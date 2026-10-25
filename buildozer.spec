[app]
title = LocalChat
package.name = localchat
package.domain = org.localchat
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,json
source.exclude_dirs = bin,.git,.github,__pycache__,.buildozer
version = 1.0
requirements = python3,kivy,requests,urllib3,chardet,idna,certifi,pyjnius
orientation = portrait
android.permissions = INTERNET,com.termux.permission.RUN_COMMAND,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE
android.add_assets = bin/llama-server:llama-server
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
