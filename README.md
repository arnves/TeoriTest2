# TeoriTest2 🚗

En moderne og adaptiv teoriprøve for førerkort klasse B, bygget for å fungere 100% i nettleseren uten behov for en backend.

## ✨ Funksjoner

- **Adaptiv Læring**: Appen justerer automatisk vanskelighetsgraden (Easy/Medium/Hard) basert på dine svar i hver kategori.
- **Spørsmålsmestring**: Spørsmål du har svart riktig på 3 ganger på rad blir markert som "mestret" og fjernet fra rotasjon, slik at du kan fokusere på det du ikke kan.
- **Komplett Databank**: Inneholder hundrevis av spørsmål generert mot det offisielle pensumet.
- **Personlig Statistikk**: Følg med på din mestringsgrad per domene (Vikeplikt, Skilt, Kjøretøy, etc.).
- **100% Klient-sentrert**: Bruker `sql.js` for in-browser database og `localStorage` for lagring av din fremgang.

## 🛠 Teknologi

- **Frontend**: Vanilla JS, HTML5, CSS3.
- **Ikoner**: [Lucide](https://lucide.dev/).
- **Database**: SQLite via [sql.js](https://sql.js.org/).
- **Design**: Moderne glassmorphism med mørkt tema.

## 🚀 Kom i gang lokalt

1. Klone repoet:
   ```bash
   git clone https://github.com/arnves/TeoriTest2.git
   ```
2. Åpne mappen:
   ```bash
   cd TeoriTest2
   ```
3. Start en lokal webserver (f.eks. med Python eller npx):
   ```bash
   npx serve .
   ```
   *Merk: Databasen krever en webserver for å lastes riktig via fetch.*

## 📄 Lisens

Dette prosjektet er utviklet for personlig bruk og utdanning.
