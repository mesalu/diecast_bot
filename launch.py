#!/usr/bin/env python3

"""
"""

from bot import DieCastBot
import keyring

client = DieCastBot()
client.run(keyring.get_password("discord", "diecast_bot"))