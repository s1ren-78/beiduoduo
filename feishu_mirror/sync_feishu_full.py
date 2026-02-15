#!/usr/bin/env python3
"""Wrapper: python3 sync.py --scope feishu --mode full --reason manual"""
import sys; sys.argv = [__file__, "--scope", "feishu", "--mode", "full", "--reason", "manual"]
from sync import main; main()
