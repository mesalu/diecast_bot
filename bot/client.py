"""
"""

import discord
import time
from typing import List
import logging

from .parser import DieCastParser

# NOTE: there's a discord.ext.commands module that likely has better support for whats done here.

GREETINGS_LIST = ("Hey", "Greetings", "Hello", "Salutations", "Hola")

class DieCastBot(discord.Client):
    def __init__(self, *args, **kwargs):
        discord.Client.__init__(self, *args, **kwargs)
        self.log = logging.getLogger("BotClient")
        self.log.setLevel(logging.DEBUG)
        self._instanced_time = time.time()
        self._roll_request_counter = 0

    async def on_ready(self):
        self.log.info("Connected!")

    async def on_message(self, message: discord.Message):
        # Check to make sure that we're not processing our own outbound message, and for now only operate on #bot_playground:
        if not message.author == self.user and str(message.channel) == "bot_playground":
            # check if the message contains the magic phrase.
            chunks = message.content.strip().split()
            content = " ".join(chunks[1:])
            if chunks[0] == "!diecast":
                # figure out which handler to use.
                handlers = {
                    'roll': self._on_roll_request,
                    'status': self._on_status_request
                }

                command = chunks[1]

                try:
                    handler = handlers[command]
                except KeyError:
                    # Default to servicing a roll request
                    handler = self._on_roll_request

                response = handler(content)
                await message.channel.send(f"{random.choice(GREETINGS_LIST)} {message.author.mention}! " + response)

            else:
                self.log.debug(f"Incoming message from '{message.author}' is not interesting.")
                return

    async def _on_roll_request(self, msg_contents: str) -> str:
        """
        Invoked to handle roll requests
        :param List[str] msg_contents: array of strings containing whitespace-split input from user
        :returns: the response to send back to the user.
        :rtype: str
        """
        self.log.info(f"Processing diecast request from: '{message.author}'")
        self.log.debug(f"{message.author} has requested a roll of: '{content}'")

        # Check some corner cases:
        if any((x in content for x in ('*', '/', '%', '(', ')'))):
            response = f"Hey {message.author.mention}, my programmer is a simple (if lazy) man, and did not want to deal with parse trees. Please keep your requests to simple addition and subtraction arithmetic."
            await message.channel.send(response)
            return

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

        # Report back to user:
        return response


