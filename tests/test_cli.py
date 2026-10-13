"""Unit tests for the CLI interface and argument parsing."""

import argparse
import pytest
from rdr_transit.cli import build_parser


def test_cli_parser_subcommands():
    parser = build_parser()
    subparsers_action = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ][0]
    subcommand_names = set(subparsers_action.choices.keys())

    assert "tui" in subcommand_names
    assert "send" in subcommand_names
    assert "receive" in subcommand_names
    assert "snippet" in subcommand_names
    assert "config" in subcommand_names
    assert "discover" in subcommand_names
    # GUI should not be present
    assert "gui" not in subcommand_names


def test_cli_parser_send_args():
    parser = build_parser()
    args = parser.parse_args(["send", "file1.txt", "-t", "192.168.1.50", "-p", "17116", "-j", "4"])
    assert args.subcommand == "send"
    assert args.paths == ["file1.txt"]
    assert args.target == "192.168.1.50"
    assert args.port == 17116
    assert args.parallel == 4


def test_cli_parser_receive_args():
    parser = build_parser()
    args = parser.parse_args(["receive", "--port", "18000", "--no-skip", "--no-verify"])
    assert args.subcommand == "receive"
    assert args.port == 18000
    assert args.no_skip is True
    assert args.no_verify is True


def test_cli_parser_snippet_args():
    parser = build_parser()
    args = parser.parse_args(["snippet", "hello world", "-t", "192.168.1.50"])
    assert args.subcommand == "snippet"
    assert args.text == "hello world"
    assert args.target == "192.168.1.50"
