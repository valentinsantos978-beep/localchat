# LocalChat

Chat com IA local (GGUF) rodando dentro do APK. O Termux só é necessário se você usar
os comandos de shell (/run, /ls, /read).

## Como usar

1. Baixe o APK na aba **Actions** (artifact \`localchat-apk\`).
2. Instale no celular.
3. Coloque seus \`.gguf\` em \`/sdcard/Download/\`.
4. Abra o app, conceda "Acesso a todos os arquivos".
5. Toque em **Modelo** e escolha um GGUF.

## Se o build falhar

Baixe o artifact \`build-log\` do run e veja as ultimas 200 linhas.
Os dois pontos mais comuns:

- \`llama-server\` nao compilou (target/flag incompatível com a tag do llama.cpp).
  Nesse caso o workflow ja remove \`android.add_assets\` do spec e o APK sai mesmo
  assim — so sem IA local.
- \`buildozer\` falhou por falta de dependencia do sistema. Veja o erro exato no log.

## Comandos dentro do chat

- Mensagem normal → IA local com streaming.
- \`/run <cmd>\` → shell no Termux (abre popup se nao estiver conectado).
- \`/ls <path>\` → lista diretorio no Termux.
- \`/read <path>\` → le arquivo no Termux.

## RAM

- 4 GB → ate ~3B Q4
- 8 GB → ate ~7B Q4
- 12 GB+ → ate ~13B Q4
