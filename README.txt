
FEITAL | GESTÃO DE ATIVOS - BUILD 01
====================================

Esta é a primeira versão responsiva para uso em celular, tablet ou computador.

LOGIN INICIAL
-------------
Usuário: admin
Senha: admin123

IMPORTANTE:
Troque essas credenciais antes de colocar o sistema em uso definitivo.

COMO INSTALAR
-------------
1. Instale Python 3.11 ou superior.
2. Abra o Prompt de Comando dentro desta pasta.
3. Execute:

   pip install -r requirements.txt

4. Inicie:

   streamlit run app.py --server.address 0.0.0.0

5. No computador, abra:
   http://localhost:8501

ACESSAR PELO CELULAR NA MESMA REDE
----------------------------------
1. Descubra o IP do computador com:
   ipconfig

2. Procure o "Endereço IPv4", por exemplo:
   192.168.1.50

3. No celular conectado ao mesmo Wi-Fi, abra:
   http://192.168.1.50:8501

4. Se o Windows Firewall perguntar, permita o acesso em redes privadas.

A Build 01 inclui:
- Login responsivo
- Dashboard
- Cadastro de equipamentos
- Nova Entrega
- Devolução
- Consulta por patrimônio/modelo/série/IMEI
- Histórico de movimentações
- Banco SQLite local

Próximas builds sugeridas:
- Assinatura com o dedo na tela
- Fotos pela câmera do celular
- PDF automático do termo
- QR Code no patrimônio
- Envio por e-mail
- Integração com Active Directory
