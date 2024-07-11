from __future__ import annotations
import os, sys
import subprocess as sp
import re
import shutil
import glob

import argparse
import importlib
import json

from typing import List, Tuple, Dict, Any, Callable, Sequence

import pytest
import inspect

import src.common.data_structs as rg_ds
import tests.common.common as tests_common


def run_pytest(*args):
    print("-vv","-s", *args)
    return pytest.main(["-vv","-s", *args])


def main():
    args = sys.argv[1:]
    return run_pytest(*args)

if __name__ == "__main__":
    main()

