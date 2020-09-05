#!/usr/bin/env python3

"""
Quick launch point for the bot program.
"""

from bot import DieCastBot
import keyring

if __name__ == "__main__":
    client = DieCastBot()
    client.run(keyring.get_password("discord", "diecast_bot"))