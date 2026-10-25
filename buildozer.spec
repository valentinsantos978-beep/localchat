[app]
title = LocalChat
package.name = localchat
package.domain = org.localchat
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,json
version = 1.0
requirements = python3,kivy,requests,urllib3,chardet,idna,certifi
orientation = portrait
android.permissions = INTERNET,com.termux.permission.RUN_COMMAND,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
