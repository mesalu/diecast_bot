"""
"""

import datetime
import discord
import logging
import random
import time
from typing import List

from .parser import DieCastParser

# NOTE: there's a discord.ext.commands module that likely has better support for whats done here.

GREETINGS_LIST = ("Hey", "Greetings", "Hello", "Salutations", "Hola")

class DieCastBot(discord.Client):
    class _HandlerContext(object):
        def __init__(self, sender: discord.Member, channel: discord.TextChannel, message: discord.Message):
            self.sender = sender
            self.channel = channel
            self.raw_message = message

    def __init__(self, *args, **kwargs):
        discord.Client.__init__(self, *args, **kwargs)
        logging.basicConfig()
        self.log = logging.getLogger("BotClient")
        self.log.setLevel(logging.DEBUG)
        self._instanced_time = time.time()
        self._roll_request_counter = 0

        self._blacklisted = set()

    async def on_ready(self):
        self.log.info("Connected!")

    async def on_message(self, message: discord.Message):
        # Check to make sure that we're not processing our own outbound message, and for now only operate on #bot_playground:
        if not message.author == self.user and str(message.channel) == "bot_playground" and message.author.id not in self._blacklisted:

            # check if the message contains the magic phrase.
            chunks = message.content.strip().split()
            content = " ".join(chunks[1:])
            if chunks[0] == "!diecast":
                # figure out which handler to use.
                handlers = {
                    'greetings': self._on_greetings,
                    'hello': self._on_greetings,
                    'hi': self._on_greetings,
                    'hey': self._on_greetings,
                    'roll': self._on_roll_request,
                    'status': self._on_status_request,
                    'blacklist': self._on_blacklist,
                    'block': self._on_blacklist,
                    'release': self._on_blacklist_remove
                }

                command = chunks[1].lower()

                try:
                    handler = handlers[command]
                    content = ' '.join(chunks[2:])
                except KeyError:
                    # Default to servicing a roll request
                    handler = self._on_roll_request

                ctx = DieCastBot._HandlerContext(message.author, message.channel, message)
                response = handler(ctx, content)
                await message.channel.send(f"{random.choice(GREETINGS_LIST)} {message.author.mention}! " + response)

            else:
                self.log.debug(f"Incoming message from '{message.author}' is not interesting.")
                return

    def _on_greetings(self, ctx, msg_contents: str) -> str:
        return ""

    def _on_status_request(self, ctx, msg_contents: str) -> str:
        # currently too lazy to find the built in way to do this, so here goes:
        delta = int(time.time() - self._instanced_time)
        sec_per_min = 60
        sec_per_hr  = 3600
        sec_per_day = sec_per_hr * 24

        seconds = delta % 60
        minutes = (delta // sec_per_min) % 60 # minutes in an hour (next increment)
        hours = (delta // sec_per_hr) % 24    # hours per day
        days = delta // sec_per_day

        elapsed = f"{f'{days} days ' if days else ''}{f'{hours} hours ' if hours else ''}{f'{minutes} minutes ' if minutes else ''}{f'{seconds} seconds' if seconds else ''}"

        # adjust min and
        return f"I have been running for: {elapsed}, and I have serviced {self._roll_request_counter} roll requets!"

    def _on_roll_request(self, ctx, msg_contents: str) -> str:
        """
        Invoked to handle roll requests
        :param List[str] msg_contents: array of strings containing whitespace-split input from user
        :returns: the response to send back to the user.
        :rtype: str
        """
        self.log.debug(f"Inbound request string: {msg_contents}")

        # Parse the request and act on it
        total = 0       # total from die cast.
        components = [] # Individual die casts & constant modifier
        response = f"This is an uninitialized response. Something went really weird on my end. :("

        try:
            tree = DieCastParser(msg_contents)

        except DieCastParser.ParseError:
            response =  f"I encountered an error parsing your diecast request. Please try again."

        else:
            scalar = 1 # will be changed to -1 on subtractions.
            const_total = 0
            num_casts = 0

            # Use the parse tree's walk_terminals function to process the input:
            for node in tree.walk_terminal_nodes():
                if node.type == "operator":
                    scalar = 1 if node.raw == "+" else -1 # NOTE: this line will be problematic if other operators added.

                if node.type == "constant":
                    const_total += (scalar * int(node.raw))

                if node.type == "adv":
                    # this is a special clause:
                    functor = min if node.raw == "dis" else max
                    rolls = [random.randint(1, 20) for _ in range(2)]
                    result = scalar * functor(rolls)
                    total += result
                    components.append(rolls)
                    num_casts += 2

                if node.type == "diecast":
                    # check to make sure this request isn't going to take a millenia to service.
                    # The parser leaves these fields as strings, and doesn't accept characters
                    # exceeding those in base 10 for the value, so we'll use that property
                    # to make sure the die count and size are manageable.
                    if len(node.n) > 5:
                        return "I am fearful to try and roll this many dice! My virtual table may crumple."
                    if len(node.size) > 6:
                        return "They make dice that big!? Unfortunately my virtual environment doesn't have enough voxels to make out the letters on that dice, so I can't help you."

                    # now that those fields are loosely validated we'll read and use them
                    # as base-10 integers
                    node.n = int(node.n)
                    node.size = int(node.size)

                    num_casts += node.n
                    if node.n > 1:
                        # we'll be looping and grouping
                        group = [scalar * random.randint(1, node.size) for _ in range(node.n)]
                        total += sum(group)
                        components.append(group)
                    else:
                        result = scalar * random.randint(1, node.size)
                        total += result
                        components.append(result)

            # Tack on the constant portion.
            components.append(const_total)
            total += const_total

            response = f"I {'rolled' if num_casts else 'computed'} a total of: {total}!"
            if num_casts < 25: # Show at most 25 items in the report, TODO: make this configurable via CLI.
                response += f" ({', '.join( (str(x) for x in components) )})"

            # Track the success of a roll request:
            self._roll_request_counter += 1

        # Report back to user:
        return response

    def _on_blacklist(self, ctx, msg_contents: str) -> str:
        # TODO: save blacklist to a permanent file, restore on relaunch.

        is_admin = ctx.sender.permissions_in(ctx.channel)

        if not is_admin:
            return "Sorry, you need to be a server admin to use this feature. This attempt has not been recorded nor will it be reported to your system admin."

        # find the mentions within the message.
        to_blacklist = [x.id for x in ctx.raw_message.mentions]

        if not to_blacklist:
            return "I cannot add nobody to the blacklist, please use mentions to specify users (That way we don't make mistakes.)"

        self._blacklisted.update(to_blacklist)
        return f"I have added [{', '.join([x.display_name for x in ctx.raw_message.mentions])}] to the blacklist, which now contains {len(self._blacklisted)} entries."

    def _on_blacklist_remove(self, ctx, msg_contents: str) -> str:
        is_admin = ctx.sender.permissions_in(ctx.channel)

        if not is_admin:
            return "Sorry, you need to be a server admin to use this feature. This attempt has not been recorded nor will it be reported to your system admin."

        to_release = [x for x in ctx.raw_message.mentions if x.id in self._blacklisted]

        if not to_release:
            if ctx.raw_message.mentions:
                return "No mentioned users were in the blacklist."
            else:
                return "Please specify, with mentions, which users you wish to remove from the blacklist."

        self._blacklisted.difference_update([x.id for x in to_release])

        base_reply = f"I have removed [{', '.join([x.display_name for x in to_release])}] to the blacklist, which now contains {len(self._blacklisted)} entries.\n"
        return base_reply + '\n'.join([f'Welcome back {x.mention}' for x in to_release])
