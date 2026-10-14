# Webspace fuer AHPT auswaehlen

Dieser Text sagt dir, **welcher Webspace sich fuer AHPT eignet** und bei
welchen Hostern das praktisch getestet wurde. Es ist kein Verkaufsprospekt
und nicht gegen Geld entstanden -- die Reihenfolge ist meine ehrliche
Empfehlung in dieser Reihenfolge.

Stand: Oktober 2026.

---

## Was AHPT vom Webspace verlangt

Erstaunlich wenig. **Alles was AHPT braucht, hat jeder PHP-Webspace von
Haus aus** -- es gibt keine Spezialanforderung, keine Datenbank, keinen
Cronjob, keine Websockets:

- **PHP 7.4 oder neuer** -- getestet bis PHP 8.3.
- **`.htaccess` wird gelesen** (fast immer Apache, bei NGINX siehe unten).
- **Mindestens 10 MB freier Platz** -- Fragen und Antworten werden sofort
  wieder geloescht, es wachsen nur Logs.
- **Keine Pflicht-Werbe-Einblendung** in deine HTML-Seiten. Die stoert
  nicht AHPT selbst (der Vermittler ist eine `.php`), aber dein Portal
  (`index.html`) kaeme sonst mit Fremdcode zurueck.
- **HTTPS** -- bei allen genannten Hostern per Let's Encrypt gratis dabei.

Was du **nicht** brauchst: SSH-Zugang, Shell, cron, root, eigene IP,
Domain. Der Hoster-eigene Subdomain-Name (`deinname.bplaced.net`) reicht.

**Mindest-Testbefehl** nach der Einrichtung (lokal, nicht am Hoster):

```bash
curl -I https://deinname.hoster.tld/relay.php
```

HTTP 200 oder 405 heisst "funktioniert", 403 oder 500 heisst "PHP wurde
nicht ausgefuehrt oder .htaccess greift falsch" -- siehe
`htaccess-beispiel`.

---

## Freie Hoster -- getestet

### 1. lima-city.de -- Erste Wahl

- **Rechenzentrum:** Deutschland (Nuernberg).
- **PHP:** 8.3 waehlbar.
- **Platz:** 10 GB freier Webspace, keine Traffic-Grenze.
- **Werbung in HTML:** nein.
- **Login-Pflicht zum Wachhalten:** keine -- der Account bleibt bestehen,
  solange du nicht aktiv kuendigst.
- **Dateimanager im Backend:** ja (ZIP-Upload und Entpacken direkt im
  Browser -- bequemster Weg fuer das AHPT-Paket).
- **FTP/SFTP:** ja, Login-Daten direkt im Backend sichtbar.
- **HTTPS:** Let's Encrypt gratis, automatisch.
- **Besonderheit:** `.htaccess` greift ab Werk, mod_speling ist bereits
  aus -- der kritischste Punkt (siehe `htaccess-beispiel`) ist bei
  lima-city nie ein Problem gewesen.

**Einziger Haken:** Registrierung braucht eine Mail-Verifikation und ein
kurzes Captcha. Danach freigeschaltet in unter einer Minute.

### 2. bplaced.net -- bewaehrt, erfordert etwas Aufmerksamkeit

- **Rechenzentrum:** Deutschland.
- **PHP:** 7.4 bis 8.2 waehlbar.
- **Platz:** 500 MB, 5 GB Traffic/Monat.
- **Werbung in HTML:** nein (bei "Free"-Account auch 2026 nicht).
- **Login-Pflicht:** mindestens einmal pro **90 Tage** im Backend
  einloggen, sonst wird der Account geloescht. Kalendereintrag anlegen.
- **Dateimanager:** ja.
- **FTP/SFTP:** ja.
- **HTTPS:** Let's Encrypt gratis.
- **Besonderheit:** Hier wurde AHPT entwickelt und monatelang betrieben.
  Alle Fehler, die `htaccess-beispiel` adressiert, wurden auf bplaced
  entdeckt und dort nachgemessen.

**Haken:** Der 90-Tage-Timer ist ernst. Wenn der Account weg ist, ist
auch der AHPT-Vermittler weg -- und deine App ist nicht erreichbar bis
du einen neuen Hoster hast und den Agent darauf umkonfigurierst.

### 3. ohost.de -- Backup, nicht Erstwahl

- **Rechenzentrum:** Deutschland.
- **PHP:** 8.1.
- **Platz:** 1 GB.
- **Werbung in HTML:** nein.
- **Dateimanager:** ja, allerdings etwas gewoehnungsbeduerftig.
- **Besonderheit:** `.htaccess` wird gelesen, aber `FileETag INode MTime
  Size` wird teilweise ignoriert -- siehe die Erklaerung in
  `htaccess-beispiel`, Abschnitt 4. Fuer AHPT praktisch verkraftbar, weil
  die anderen drei Schranken wirken, aber auf lima-city und bplaced ist
  die Lage sauberer.

---

## Hoster, die **nicht** gehen

Vollstaendigkeitshalber -- bitte spar dir die Zeit:

- **GitHub Pages, Netlify, Vercel, Cloudflare Pages:** reine Statik oder
  Serverless -- kein PHP, auch nicht mit Umweg.
- **npwd.de, kilu.de und einige kleinere:** blenden Werbung in `.html`
  ein, die Portal-Seite kaeme mit fremdem JavaScript zurueck.
- **000webhost.com (international):** schaltet den Space nach kurzer
  Inaktivitaet ab, `.htaccess` wird teilweise ignoriert, Werbung an.
- **Jeder "NGINX ohne .htaccess"-Hoster:** `.htaccess` wird nicht gelesen,
  die Sicherheitsregeln aus `htaccess-beispiel` wirken nicht. Die
  `.php`-Endung alleine traegt zwar den Zugriffsschutz, aber mod_speling
  hat auf NGINX kein Gegenstueck -- in dem Fall sind die Pfade zu
  `relay_token.php`/`relay_state.php` in `relay.php` als Konstanten weit
  ausserhalb des DocumentRoot zu legen (siehe Kommentar unten in
  `htaccess-beispiel`).

---

## Bezahlte Hoster

Wenn du schon einen Webspace bezahlst (All-Inkl, Netcup, Hetzner Konsol,
Strato, 1und1): **nutze den.** AHPT laeuft dort erstklassig und du hast
den Betrieb ohnehin schon unter Kontrolle. Kein Grund wegen AHPT allein
ein kostenpflichtiges Angebot zu buchen.

---

## Wie du wechseln kannst

Falls dein Hoster dich enttaeuscht: Der Vermittler ist zustandslos. Du
brauchst nur:

1. Neues Webspace-Paket (`.htaccess`, `relay.php`, `ahpt/.htaccess`) auf
   dem neuen Hoster entpacken.
2. In Ilija unter `Einstellungen -> AHPT -> Relay-Basis-URL` die neue URL
   eintragen und speichern.
3. Agent neu starten.

Die bereits gekoppelten Handys muessen **einmal neu gekoppelt werden**
(QR scannen) -- ihre Agent-Keys bleiben gueltig, aber die Relay-URL ist
in der App fest hinterlegt.
