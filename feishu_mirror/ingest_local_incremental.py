#!/usr/bin/env python3
"""Wrapper: python3 sync.py --scope local --mode incremental --reason schedule"""
import sys; sys.argv = [__file__, "--scope", "local", "--mode", "incremental", "--reason", "schedule"]
from sync import main; main()
