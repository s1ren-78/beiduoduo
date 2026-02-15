#!/usr/bin/env python3
"""Wrapper: python3 sync.py --scope all --mode full --reason schedule"""
import sys; sys.argv = [__file__, "--scope", "all", "--mode", "full", "--reason", "schedule"]
from sync import main; main()
