# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['src/opencode_telegram_bot/launcher.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/opencode_telegram_bot/locales', 'opencode_telegram_bot/locales'),
    ],
    hiddenimports=[
        'opencode_telegram_bot.api',
        'opencode_telegram_bot.api.client',
        'opencode_telegram_bot.api.server',
        'opencode_telegram_bot.bot',
        'opencode_telegram_bot.bot.handler',
        'opencode_telegram_bot.core',
        'opencode_telegram_bot.core.config',
        'opencode_telegram_bot.core.session',
        'opencode_telegram_bot.utils',
        'opencode_telegram_bot.utils.i18n',
        'opencode_telegram_bot.utils.scheduler',
        'opencode_telegram_bot.utils.voice',
        'opencode_telegram_bot.gui',
        'opencode_telegram_bot.web',
        'opencode_telegram_bot.web.gui',
        'telegram',
        'telegram.ext',
        'telegram.ext.filters',
        'customtkinter',
        'flask',
        'apscheduler',
        'httpx',
        'dotenv',
        'pydantic',
        'pydantic_settings',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter.tests', 'PIL.ImageDraw', 'PIL.ImageFont'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='tp-opencode',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='tp-opencode',
)
