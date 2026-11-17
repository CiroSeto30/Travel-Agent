// A fake agent that emits the same events as the real chat endpoint (docs/design.md §10).
// It lets the chat page be built and tried before the agent exists; chat.js stops using it in feat/agent.

import { euro } from "./format.js";
import { OPTIONS, currentTotal, markItinerary } from "./mock-itineraries.js";

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

let proposalSet = 0;
let pending = null;

async function* say(text) {
  for (const word of text.split(/(?<= )/)) {
    await wait(25);
    yield { event: "token", data: { text: word } };
  }
}

export function welcome(user) {
  return (
    `Ciao ${user.first_name}! Posso organizzare viaggi in Giappone, Spagna, Grecia, Portogallo, Francia, ` +
    "Islanda, Regno Unito, Paesi Bassi, Thailandia, Stati Uniti e Italia. " +
    "Dimmi dove vorresti andare, in che mese, per quante notti, in quanti siete e con che budget."
  );
}

export async function* mockReply(text) {
  if (/^(s[iì]|confermo|ok)(?!\p{L})/iu.test(text.trim()) && pending) {
    yield { event: "tool_start", data: { tool: "book", label: "Prenoto voli, hotel e attività" } };
    await wait(900);
    yield { event: "tool_end", data: { tool: "book" } };
    markItinerary(pending.itinerary_id, "booked");
    yield { event: "booking", data: { booking_id: 1, itinerary_id: pending.itinerary_id, status: "confirmed" } };
    yield* say(`Fatto: l'opzione ${pending.variant.toLowerCase()} è prenotata. La trovi in "Le mie prenotazioni".`);
    pending = null;
  } else if (/prenota/i.test(text) && proposalSet > 0) {
    const options = OPTIONS[proposalSet - 1];
    pending = options.find((o) => text.toLowerCase().includes(o.variant.toLowerCase())) ?? options[0];
    yield* say(
      `Riepilogo: ${pending.city}, opzione ${pending.variant.toLowerCase()}, hotel ${pending.hotel}, ` +
      `${pending.travelers} persone, ${euro(currentTotal(pending.itinerary_id))} in tutto. ` +
      "Confermi la prenotazione?",
    );
  } else if (proposalSet === OPTIONS.length) {
    yield* say("Queste sono le opzioni migliori che ho trovato. Apri i dettagli o dimmi quale vuoi prenotare.");
  } else {
    const index = proposalSet;
    const supersedes = proposalSet > 0 ? `set-${proposalSet}` : null;
    yield { event: "requirements", data: { country: "Giappone", month: 4, nights: 6, travelers: 2,
      budget: "4000.00", origin: "NAP", preferences: ["cultura", "cibo"], missing: [] } };
    yield { event: "tool_start", data: { tool: "search_itineraries", label: "Cerco voli, hotel e attività" } };
    await wait(1200);
    yield { event: "tool_end", data: { tool: "search_itineraries" } };
    yield* say(supersedes
      ? "Spostando il viaggio di una settimana si risparmia qualcosa. Ecco le nuove opzioni."
      : "Ecco tre itinerari per il Giappone, dal 10 al 16 aprile, partendo da Napoli.");
    for (const option of OPTIONS[proposalSet - 1] ?? []) markItinerary(option.itinerary_id, "superseded");
    proposalSet = index + 1;
    yield { event: "itinerary", data: { proposal_set_id: `set-${proposalSet}`, supersedes, options: OPTIONS[index] } };
    yield* say("Apri i dettagli per vedere il programma giorno per giorno.");
  }
  yield { event: "done", data: { message_id: Date.now() } };
}