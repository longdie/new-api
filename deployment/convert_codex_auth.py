#!/usr/bin/env python3
"""Convert a local Codex auth.json into a New API Codex channel credential.

Uses only the Python standard library. No network requests, login, token refresh,
or credential logging. Output is created with mode 0600 and never overwritten.
Only the JSON structure is checked; validity and expiry require an upstream test.

Credential-handling references (not a full ASVS compliance assessment):
https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html

Usage:
    python deployment/convert_codex_auth.py /path/to/auth.json
    python deployment/convert_codex_auth.py /path/to/auth.json -o /path/to/output.json
"""

import argparse
import json
import os
from pathlib import Path
import sys


def convert_auth(auth: object) -> dict[str, str]:
    """Keep only the fields required for requests and credential refresh."""
    if not isinstance(auth, dict):
        raise ValueError("auth.json 的顶层必须是 JSON 对象。")
    tokens = auth.get("tokens")
    if not isinstance(tokens, dict):
        raise ValueError("缺少 tokens 对象；请使用通过 ChatGPT 登录生成的 auth.json。")

    credential = {"type": "codex"}
    for field in ("access_token", "refresh_token", "account_id"):
        value = tokens.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"tokens.{field} 必须是非空字符串。")
        credential[field] = value.strip()

    last_refresh = auth.get("last_refresh")
    if last_refresh is not None:
        if not isinstance(last_refresh, str) or not last_refresh.strip():
            raise ValueError("last_refresh 必须是非空字符串，或省略该字段。")
        credential["last_refresh"] = last_refresh.strip()
    return credential


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="将 Codex auth.json 转换为 New API 渠道凭据；离线运行且不显示密钥。",
        epilog="仅检查文件格式，不验证账号权限、Token 有效期或网络连通性。",
    )
    parser.add_argument("input", type=Path, help="通过 ChatGPT 登录生成的 auth.json 路径")
    parser.add_argument(
        "-o", "--output", type=Path,
        help="输出路径，默认在输入文件旁生成 new-api-credential.json；已有文件不会被覆盖",
    )
    args = parser.parse_args(argv)

    try:
        source = args.input.expanduser()
        target = (
            args.output.expanduser()
            if args.output is not None
            else source.with_name("new-api-credential.json")
        )
        if source.resolve() == target.resolve():
            raise ValueError("输入和输出不能是同一文件；请指定其他输出路径。")

        # Never include input contents or JSON parser exception details in logs.
        auth = json.loads(source.read_text(encoding="utf-8-sig"))
        payload = json.dumps(convert_auth(auth), ensure_ascii=True, indent=2) + "\n"
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

        # O_EXCL also rejects existing symlinks, including dangling symlinks.
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(payload)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    except FileExistsError:
        print("错误：输出文件或父路径已存在且不可新建；请用 -o 指定新的文件名。", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print("错误：找不到输入文件或目录，请检查路径。", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, UnicodeError):
        print("错误：输入文件不是有效的 UTF-8 JSON；未输出文件内容。", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1
    except OSError:
        print("错误：文件读写失败，请检查路径、访问权限和剩余磁盘空间。", file=sys.stderr)
        return 1

    print(f"转换完成：{target.absolute()}")
    print("输出权限：仅当前用户可读写（0600 或更严格）；输入文件未修改。")
    print("请在编辑器中打开输出文件，将完整 JSON 粘贴到 New API Codex 渠道的密钥字段。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
