#!/usr/bin/env python3

import discord
import keyring
import logging
import random
import re

# NOTE: there's a discord.ext.commands module that likely has better support for whats done here.
# NOTE: the grammar isn't totally perfect, even for its meager targets. For example:
#       leading hyphens (for negative values) will be treated as an error.

GREETINGS_LIST = ("Hey", "Greetings", "Hello", "Salutations", "Hola")
RE_VALID   = re.compile(r"[\s\d+-d]*") # Not used after adding advantage and disadvantage rule.
logging.basicConfig(level=logging.WARNING)

# TODO: most of the functions in this class boil down to a try-except-fail pattern.
#       which I suspect could be more efficient.
class DieCastParser(object):
    """
    Parses a diecast string.

    Reiteration of grammar being targetted:
    S -> expr
    expr -> eps. | term | term term_tail
    term -> diecast | constant | adv
    term_tail -> eps. | op expr
    constant -> (\d+)
    op -> [+-]
    diecast -> ((\d*)\s*d\s*(\d+))
    adv -> 'adv' | 'advantage' | 'dis' | 'disadvantage'
    """
    # TODO: review notes and re-work this (if needed) to be in chomsky normal form.

    class ParseError(Exception): pass
    class NoTreeError(Exception): pass

    class ParseNode(object):
        def __init__(self, text: str, type: str):
            self.raw = text
            self.type = type
            self.children = []

        def __repr__(self):
            return f"<ParseNode<{repr(self.type)}> object>"

        def add_child(self, child):
            if not isinstance(child, DieCastParser.ParseNode):
                raise TypeError

            self.children.append(child)

    def __init__(self, text: str):
        self._raw = text
        self._start(text)

    def walk_terminal_nodes(self):
        """
        Iterates over terminal nodes in the parse tree in (L)NR order.
        Note that as implemented there aren't really 'left' nodes, so its
        mostly a node-right traversal.
        """
        if self._tree is None:
            raise DieCastParser.NoTreeError

        # Use a private method to do the actual generating (just return the generator here)
        return self._walk(self._tree)


    def _walk(self, node):
        """
        Recursively walks through the node's tree structure yielding (and subyielding) terminal nodes
        as it discovers them.
        """
        terminal_types = ("constant", "operator", "diecast", "adv")

        if node.type in terminal_types:
            yield node

        for child in node.children:
            yield from self._walk(child)

    # The following methods service precisely one of the nonterminal (variable? man, grammar design class seems so long ago. Thanks 2020)
    # Each of these methods will take a single input string and (except for _start) return a tuple of a ParseNode and a  string - or throw an error.
    # the first will be what they successfully matched, the latter will be the remainder of the string.
    # If a function determines that it cannot correctly parse its input then a ParseError will be thrown.
    def _start(self, text: str):
        """
        Parses the start variable.

        S -> expr
        """
        self._tree, _ = self._expr(self._raw)

    def _expr(self, text: str):
        """
        Parses the expression variable.

        expr -> eps. | term | term term_tail
        """
        # Handle epsilon:
        if not text:
            return None, None

        node = DieCastParser.ParseNode(text, "expression")
        extra = None

        subnode, opt = self._term(text)
        node.add_child(subnode)

        if opt:
            opt, extra = self._term_tail(opt)
            node.add_child(opt)

        return node, extra

    def _term(self, text: str):
        """
        Parses the term variable

        term -> diecast | constant | adv
        """
        node = DieCastParser.ParseNode(text, "term")

        # Spooky pyramid of death
        try:
            child, extra = self._diecast(text)
        except DieCastParser.ParseError:
            try:
                child, extra =  self._const(text)
            except DieCastParser.ParseError:
                child, extra = self._adv(text)

        node.add_child(child)
        return node, extra

    def _term_tail(self, text: str):
        """
        Parses the tail end of an expression, if necessary.

        term_tail -> eps. | op expr
        """
        # handle epsilon case:
        if not text:
            return None, None

        node = DieCastParser.ParseNode(text, "term_tail")

        op, rest = self._op(text)
        second_expr, rest = self._expr(rest)

        node.add_child(op)
        node.add_child(second_expr)

        return node, rest

    def _const(self, text: str):
        """
        Parses the constant-value variable.

        constant -> (\d+)
        """
        text = text.strip()

        # For now lets just do a linear scan looking for non-numerical characters.
        i = 0
        while i < len(text) and text[i] in [str(x) for x in range(10)]:
            i += 1

        if i == 0:
            raise DieCastParser.ParseError(f"Expected literal constant (got: {repr(text)})") # got something that isn't a number.

        node = DieCastParser.ParseNode(text[:i], "constant")

        return node, text[i:]


    def _op(self, text: str):
        """
        Parses the operator variable.

        op -> [+-]
        """
        text = text.strip()
        if text[0] in ('+', '-'):
            return DieCastParser.ParseNode(text[0], "operator"), text[1:]
        else:
            raise DieCastParser.ParseError("Expected operation (+ or -).")

    def _diecast(self, text: str):
        """
        Parses a diecast variable.

        diecast -> ((\d*)\s*d\s*(\d+))
        """
        text = text.strip()
        rgx = re.compile(r"((\d*)\s*d\s*(\d+))(.*)")
        # group 0: whole string (if matched, e.g. 2d8 + 234)
        # group 1: the dice (e.g. 2d8)
        # group 2: num dice (e.g. 2)
        # group 3: dice size (e.g. 8)
        # group 4: the rest. (e.g. 234)
        # Change the regex and you change this ordering and will need to fix the following calls.

        match = rgx.match(text)
        if match:
            node = DieCastParser.ParseNode(match.group(1), "diecast")
            node.n = int(match.group(2)) if match.group(2) else 1
            node.size = int(match.group(3))

        else:
            raise DieCastParser.ParseError("could not recognize dice notation")

        return node, match.group(4)

    def _adv(self, text: str):
        """
        Parses a special diecast notatoin.

        adv -> 'adv' | 'advantage' | 'dis' | 'disadvantage'
        """
        chunks = text.strip().split(maxsplit=1)
        keyword = chunks[0]
        text = chunks[1] if len(chunks) > 1 else ''

        if keyword in ('advantage', 'disadvantage', 'adv', 'dis'):
            node = DieCastParser.ParseNode(keyword[:3], 'adv')
            return node, text

        raise DieCastParser.ParseError("Expected keyphrase")


class DieCastBot(discord.Client):
    def __init__(self, *args, **kwargs):
        discord.Client.__init__(self, *args, **kwargs)
        self.log = logging.getLogger("BotClient")
        self.log.setLevel(logging.DEBUG)

    async def on_ready(self):
        self.log.info("Connected!")

    async def on_message(self, message: discord.Message):
        # Check to make sure that we're not processing our own outbound message, and for now only operate on #bot_playground:
        if not message.author == self.user and str(message.channel) == "dnd":
            # check if the message contains the magic phrase.
            chunks = message.content.strip().split()
            content = " ".join(chunks[1:])
            if chunks[0] == "!diecast":
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
                    tree = DieCastParser(content)

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
                await message.channel.send(f"{random.choice(GREETINGS_LIST)} {message.author.mention}! " + response)

            else:
                self.log.debug(f"Incoming message from '{message.author}' is not interesting.")
                return

if __name__ == "__main__":
    client = DieCastBot()
    client.run(keyring.get_password("discord", "diecast_bot"))
