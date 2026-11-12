"""
QuantX — Operator command line.

Privileges that no API route can grant are managed here, by someone with
access to the server and the database.

    python -m app.cli grant-live-trading  trader@example.com
    python -m app.cli revoke-live-trading trader@example.com
    python -m app.cli list-live-traders

Live trading places orders on the operator's own exchange account. Sign-up is
open, so the permission is off for every account until it is granted here.
"""

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.database import dispose_engine, get_session_factory
from app.models.user import User


async def _set_live_trading(email: str, allowed: bool) -> int:
    async with get_session_factory()() as session:
        user = (await session.execute(select(User).where(User.email == email.lower().strip()))).scalar_one_or_none()
        if user is None:
            print(f"No account with email {email!r}.", file=sys.stderr)
            return 1
        user.can_trade_live = allowed
        await session.commit()
        print(f"Live trading {'GRANTED to' if allowed else 'REVOKED from'} {user.email} ({user.id}).")
        return 0


async def _list_live_traders() -> int:
    async with get_session_factory()() as session:
        users = (
            (await session.execute(select(User).where(User.can_trade_live.is_(True)).order_by(User.email)))
            .scalars()
            .all()
        )
        if not users:
            print("No account has live trading enabled.")
        for user in users:
            print(f"{user.email}\t{user.id}\t{'active' if user.is_active else 'DEACTIVATED'}")
        return 0


async def _run(args: argparse.Namespace) -> int:
    try:
        if args.command == "grant-live-trading":
            return await _set_live_trading(args.email, True)
        if args.command == "revoke-live-trading":
            return await _set_live_trading(args.email, False)
        return await _list_live_traders()
    finally:
        await dispose_engine()


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run one operator command."""
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="QuantX operator commands")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("grant-live-trading", "Allow an account to place orders on the exchange account"),
        ("revoke-live-trading", "Remove that permission"),
    ):
        sub = commands.add_parser(name, help=text)
        sub.add_argument("email")
    commands.add_parser("list-live-traders", help="Show every account that can place live orders")
    return asyncio.run(_run(parser.parse_args(argv)))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
