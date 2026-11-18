# Travel Assistant

Un assistente di viaggio conversazionale. Descrivi a parole il viaggio che vuoi (budget, paese, mese, notti,
viaggiatori, aeroporto di partenza, cosa ti piace) e l'assistente propone fino a tre itinerari completi: volo di
andata e ritorno, un hotel per ogni notte e attività per ogni giorno. Ogni itinerario rispetta il budget e usa solo
ciò che è davvero disponibile nelle sue date. Ne scegli uno e lo prenoti in chat; le prenotazioni compaiono in una
pagina dedicata.

Il principio guida: **l'LLM conversa, il codice garantisce.** Il modello linguistico capisce l'utente e scrive le
risposte. Validazione, ricerca, prezzi e prenotazione sono codice Python deterministico sul database: il modello non
può inventare un prezzo, una data o una disponibilità, e niente viene prenotato senza una conferma esplicita.

## Funzionalità

- Registrazione e login (password con argon2, JWT in un cookie httpOnly).
- Chat con un agente LangGraph che mantiene il contesto tra un messaggio e l'altro (stato salvato in PostgreSQL) e
  trasmette la risposta pezzo per pezzo (server-sent events).
- Requisiti estratti dal testo libero e validati in codice: un dato mancante o non valido diventa una domanda.
- Planner degli itinerari: voli, la combinazione di camere più economica per il gruppo, attività che non si
  sovrappongono, tre varianti (Economica, Bilanciata, Comfort), sempre nel budget.
- RAG: attività indicizzate in Qdrant con un modello di embedding multilingue locale, ordinate secondo le preferenze
  scritte dall'utente ("terme e buon cibo").
- Pannello dei dettagli con il programma giorno per giorno; le attività si possono scambiare, con totale e budget
  aggiornati subito e ogni regola ricontrollata dal server.
- Prenotazione solo dalla chat, dopo un riepilogo e un "sì" esplicito, in un'unica transazione con blocco delle
  righe: due utenti non possono mai ottenere l'ultima camera.
- Pagina delle prenotazioni con tutti i viaggi confermati.

## Avvio rapido (Docker)

Serve Docker Desktop e una chiave gratuita di Gemini da [Google AI Studio](https://aistudio.google.com/apikey)
(nessuna carta di credito).

```bash
cp .env.example .env
```

In `.env` compila:

- `LLM_API_KEY`: la chiave di Gemini;
- `JWT_SECRET`: una stringa casuale di almeno 32 caratteri, per esempio l'output di
  `python -c "import secrets; print(secrets.token_hex(32))"`.

Poi:

```bash
docker compose up --build
```

Apri http://localhost:8000 e registrati.

Il primo avvio richiede un paio di minuti: crea le tabelle, genera il catalogo sintetico, scarica il modello di
embedding (circa 220 MB, conservato in un volume) e indicizza le attività in Qdrant. Gli avvii successivi saltano
tutti questi passi.

Altri indirizzi: http://localhost:8000/docs (documentazione interattiva delle API), http://localhost:8000/api/health.

## Prova

Dopo la registrazione scrivi in chat, un messaggio alla volta:

1. `Vorrei andare in Giappone ad aprile` → l'assistente chiede ciò che manca.
2. `5 notti, in due, 6000 euro, da Napoli. Mi piacciono le terme e il buon cibo` → tre proposte.
3. Apri **Dettagli** su una delle proposte e scambia un'attività: totale e barra del budget si aggiornano.
4. `Prenota l'opzione bilanciata` (oppure il pulsante **Prenota questa opzione**) → riepilogo e richiesta di
   conferma.
5. `Sì, confermo` → il tagliando riceve il timbro **Prenotato** e il viaggio compare in **Le mie prenotazioni**.

Altre cose da provare: un paese che non è nel catalogo (`Australia a maggio`), un budget troppo basso (`300 euro`),
cambiare un dettaglio dopo le proposte (`meglio 4 notti`).

Destinazioni: Giappone, Spagna, Grecia, Portogallo, Francia, Islanda, Regno Unito, Paesi Bassi, Thailandia, Stati
Uniti, Italia (3 città ciascuno). Partenze: Napoli, Roma, Milano.

## Sviluppo in locale

Per avviare il backend fuori da Docker (Python 3.12+):

```bash
cp .env.example .env                 # compila LLM_API_KEY e JWT_SECRET
docker compose up -d postgres qdrant

python -m venv .venv
source .venv/Scripts/activate        # Windows (Git Bash); macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt

cd backend
python -m seed.load_db               # tabelle, tabelle di LangGraph, catalogo sintetico (una volta)
python -m seed.index_activities      # indice in Qdrant (una volta)
uvicorn app.main:app --reload
```

## Test

Dalla cartella `backend/`, con PostgreSQL acceso:

```bash
pytest
```

Circa 140 test. Usano un database separato, `travel_test`, creato in automatico, e non richiedono né una chiave API
né Qdrant: l'agente è testato con un LLM finto dalle risposte già scritte, il RAG con la modalità in memoria di
Qdrant e un embedding finto basato sulle parole. Un test usa il modello di embedding vero e viene saltato se non si
può scaricare.

I più importanti:

- il planner verificato su richieste casuali contro ogni vincolo, riletto dal database;
- la concorrenza della prenotazione su transazioni vere (ultima camera, ultimi posti, doppio clic, proposte sorelle);
- conversazioni scriptate che dimostrano che niente viene prenotato senza un riepilogo seguito da un sì.

## Struttura del progetto

```text
backend/
  app/
    agent/         requisiti e validazione, grafo LangGraph, LLM (Gemini/Groq), avvio dell'agente
    api/           router FastAPI: auth, conversazioni (stream della chat), itinerari, prenotazioni, destinazioni
    auth/          hashing delle password e token
    booking/       servizio di prenotazione (una transazione, blocco delle righe)
    db/            modelli SQLAlchemy e sessione
    itineraries/   lettura degli itinerari e scelta delle attività
    planner/       voli, camere, attività, varianti; salvataggio delle proposte
    rag/           embedding, indice Qdrant, retriever, ranker semantico
    schemas/       forme delle API (Pydantic)
  seed/            catalogo sintetico: dati di base, generazione, caricamento, indicizzazione
  tests/
frontend/          HTML, CSS e moduli JavaScript senza framework, serviti da FastAPI
docs/
  ARCHITECTURE.md  architettura e flusso di ogni azione dell'utente, con diagrammi
  design.md        documento di design: requisiti, decisioni, alternative
```

## Architettura in breve

FastAPI serve sia le API sia il frontend: niente CORS, e il cookie di login funziona senza configurazioni. PostgreSQL
contiene utenti, catalogo, itinerari, prenotazioni, conversazioni e lo stato dell'agente; Qdrant i vettori delle
attività.

Ogni messaggio della chat attraversa un grafo LangGraph: l'LLM estrae un `Turn` strutturato (cosa aggiunge il
messaggio e cosa vuole fare l'utente), il codice valida e sceglie il passo (domanda, ricerca, riepilogo,
prenotazione), e l'LLM scrive la risposta dai fatti stabiliti dal codice. Diagrammi e flusso di ogni azione sono in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); il design completo e le alternative valutate in
[docs/design.md](docs/design.md).

## Ipotesi

La spec lascia aperti alcuni punti; queste sono le scelte fatte:

- Durata del viaggio: l'assistente chiede il numero di notti (da 2 a 14) e propone 5.
- Aeroporto di partenza: chiesto in chat, tra le partenze del catalogo.
- Anno: la prossima occorrenza del mese in cui il viaggio può iniziare, da domani in poi.
- Le attività hanno un prezzo a persona, necessario per rispettare il budget.
- Viaggiatori: da 1 a 6, tutti allo stesso prezzo; le camere vengono combinate per dare un letto a tutti.
- Una sola città di destinazione per viaggio; tutto in euro; catalogo sintetico, senza fornitori reali né pagamenti.

## Limiti noti

- Un JWT non si può revocare prima della scadenza (24 ore); il logout cancella il cookie. In produzione: token brevi
  con refresh, oppure sessioni lato server.
- Ricaricando la pagina della chat si apre una nuova conversazione: i messaggi sono salvati sul server, ma la pagina
  non ricostruisce ancora le conversazioni passate.
- Una prenotazione non si può modificare né annullare.
- Il piano gratuito di Gemini consente circa 15 richieste al minuto e ogni messaggio ne usa due; un modello di riserva
  con una quota separata subentra quando quella principale finisce. In alternativa è supportato `LLM_PROVIDER=groq`.
