# Account setup (owner does this; ~1-2 days because of approvals)

1. **IC Markets demo first.** icmarkets.com -> Open account -> pick your region's entity
   -> create a *Demo* account, platform **cTrader**, type **Raw Spread**. Then the live
   account later (ID + proof of address verification, then fund).
2. **cTrader ID.** Created on first login to cTrader (web/desktop/mobile). It links to your
   IC Markets accounts. Note your **trader account number** shown in cTrader.
3. **Open API app.** openapi.ctrader.com -> sign in with the cTrader ID -> Applications ->
   add application (name, redirect URI = your Render URL + /oauth/callback). Wait for
   Spotware to activate it. Save the **Client ID** and **Client Secret**.
4. **Access token.** In the Open API "Playground" (or via the OAuth link) authorize your demo
   account, scope `trading`. Save the **access token** and **refresh token**.
5. **Telegram.** @BotFather: `/newbot` (save the token), then `/newapp` or set the menu
   button to the Render URL for the Mini App.
6. **Aiven.** Reset the database password (it was shown in a screenshot), confirm the
   service is on the free plan, copy the connection details.
7. **Render.** New Web Service from the repo; add env vars (DB URL, bot token, owner
   Telegram id, encryption key).
8. **GitHub.** Settings -> Secrets and variables -> Actions: add DB URL, bot token, key.

Never paste secrets into chat or commit them. Put them straight into Render / GitHub Secrets.
