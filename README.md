# TriaCon Brandveiligheidsinspectie

Responsive webapp voor veldinspecties op iPad en verdere rapportuitwerking op pc. Meerdere inspecteurs kunnen gelijktijdig in één centrale omgeving werken.

## Eerste start

1. Installeer Python 3.11 of nieuwer via `python.org` en kies tijdens de installatie **Add Python to PATH**.
2. Dubbelklik op `start_app.bat`.
3. Bij de eerste start wordt automatisch een lokale `.venv` gemaakt en worden de benodigde onderdelen geïnstalleerd.
4. Open op de server-pc `http://localhost:8502`.
5. Open op een iPad in hetzelfde netwerk `http://<ip-adres-van-de-pc>:8502`.

Laat het opdrachtvenster open en voorkom dat de server-pc in slaapstand gaat zolang de app beschikbaar moet blijven.

## Accounts

- Een nieuwe gebruiker kiest op het startscherm **Registreren**.
- Vereist zijn naam, e-mailadres, wachtwoord en wachtwoordbevestiging.
- Wachtwoorden worden met PBKDF2-SHA256, een unieke salt en 600.000 iteraties opgeslagen; het oorspronkelijke wachtwoord wordt nooit bewaard.
- Na inloggen kan de gebruiker via **Account en wachtwoord** het wachtwoord wijzigen of uitloggen.
- Een inactieve sessie verloopt automatisch na 12 uur.
- Alle ingelogde inspecteurs zien dezelfde projecten. De applicatie is bedoeld als gedeelde organisatieomgeving.

## Werkstructuur

De vaste hiërarchie is:

```text
Project
└─ Complex
   └─ Rapport
      └─ Bevindingen en Word-export
```

Een rapport kan alleen onder een bestaand complex worden aangemaakt. Een complex kan alleen onder een bestaand project worden aangemaakt. De sidebar en breadcrumbs tonen altijd de actieve selectie.

## Migratie en back-up

Bij de eerste start van deze versie worden rapporten uit de eerdere database automatisch gemigreerd naar de nieuwe hiërarchie. Voor de migratie wordt eenmalig deze herstelkopie gemaakt:

`data/brandveiligheid-pre-multiuser.backup.db`

Maak periodiek een back-up van:

- `data/brandveiligheid.db`
- `data/uploads`

De database gebruikt SQLite WAL-modus en een wachttijd voor gelijktijdige schrijftaken. Start slechts **één centrale appserver**. Start niet op meerdere pc's afzonderlijke appkopieën die rechtstreeks tegen hetzelfde gesynchroniseerde OneDrive-databasebestand schrijven. Voor gebruik op meerdere locaties verbinden alle inspecteurs met dezelfde server via bedrijfs-VPN of een beveiligd privénetwerk.

## Word-export

De export bewerkt `templates/rapportage_brandveiligheid_template.docx` rechtstreeks.

- Inleiding, 3.6, 3.7 en hoofdstuk 5 blijven de vaste teksten uit de template.
- In 3.2, 3.3 en 3.4 blijven labels, volgorde, opmaak en content controls uit de template behouden. Alleen de bestaande waardeslots worden ingevuld.
- In gebrekentabellen is ieder label met zijn waarde gekoppeld aan dezelfde Word-tabelrij. Meerregelige waarden kunnen volgende labels daardoor niet verticaal laten verschuiven.
- Werk na downloaden in Word de inhoudsopgave en velden zo nodig bij met `Ctrl+A` en `F9`.

## Beheer en beveiliging

- Publiceer poort 8502 niet rechtstreeks op internet.
- Gebruik voor externe toegang een VPN/Tailscale-verbinding of plaats de app achter HTTPS en centrale authenticatie.
- Open registratie staat standaard aan. Beheer daarom de netwerktoegang tot de server zorgvuldig.
- Voor een grotere cloudomgeving met meerdere serverprocessen moet SQLite worden vervangen door bijvoorbeeld PostgreSQL en moeten foto's in centrale objectopslag worden geplaatst.
