#!/usr/bin/env python3
"""Wrapper: python3 sync.py --scope market --mode incremental --reason schedule"""
import sys; sys.argv = [__file__, "--scope", "market", "--mode", "incremental", "--reason", "schedule"]
from sync import main; main()
