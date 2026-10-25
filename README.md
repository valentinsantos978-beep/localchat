# LocalChat

Chat local com modelos GGUF, streaming e agente que executa comandos no Termux.

## Como usar

1. Baixe o APK na aba **Actions** deste repositório (artifact \`localchat-apk\`).
2. Instale no celular.
3. No Termux, instale uma vez o runtime da ponte:

   \`\`\`bash
   pkg install -y python && pip install llama-cpp-python
   echo "allow-external-apps=true" >> ~/.termux/termux.properties
   \`\`\`

4. Abra o app. Se a ponte não estiver ativa, toque em **Copiar Comando** e cole no Termux
   (ou em **Conectar Automatico** se tiver concedido a permissão \`RUN_COMMAND\` ao app).

## Comandos dentro do chat

- \`/run <comando>\` — executa qualquer comando shell no Termux.
- \`/ls <path>\` — lista diretório.
- \`/read <path>\` — lê arquivo.
- \`/load <modelo.gguf>\` — carrega um modelo GGUF de \`/sdcard/Download/\`.
- Qualquer outro texto é enviado ao modelo carregado (com streaming).
