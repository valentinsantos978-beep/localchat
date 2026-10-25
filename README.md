# LocalChat

Chat com IA local (GGUF) rodando dentro do APK, sem depender do Termux para inferência.
O Termux só é necessário se você usar os comandos de shell (/run, /ls, /read).

## Como usar

1. Baixe o APK na aba **Actions** deste repositório (artifact \`localchat-apk\`).
2. Instale no celular.
3. Coloque seus arquivos \`.gguf\` em \`/sdcard/Download/\`.
4. Abra o app, conceda "Acesso a todos os arquivos" quando pedir.
5. Toque em **Modelo** e escolha um GGUF. A IA roda 100% dentro do app.

## Comandos de shell (opcional, requer Termux)

Se você digitar \`/run\`, \`/ls\` ou \`/read\` sem o Termux conectado, o app abre um popup
para você copiar o comando da ponte e colar no Termux. Também há botão para enviar
automaticamente (requer permissão RUN_COMMAND concedida).

## Comandos dentro do chat

- Mensagem normal → IA local (llama-server embutido no APK, com streaming).
- \`/run <cmd>\` → executa comando shell no Termux.
- \`/ls <path>\` → lista diretório no Termux.
- \`/read <path>\` → lê arquivo no Termux.

## RAM recomendada

- 4 GB → modelos até ~3B Q4
- 8 GB → modelos até ~7B Q4
- 12 GB+ → até ~13B Q4 (mais lento)
