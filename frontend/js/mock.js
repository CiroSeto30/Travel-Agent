// A fake agent that emits the same events as the real chat endpoint (docs/design.md §10).
// It lets the chat page be built and tried before the agent exists; chat.js stops using it in feat/agent.

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

let proposalSet = 0;
let pending = null;

const OPTIONS = [
  [
    { itinerary_id: 101, variant: "Economica", city: "Tokyo", origin: "NAP", destination: "HND",
      hotel: "Asakusa Hanabi Inn", hotel_stars: 3, start_date: "2027-04-10", end_date: "2027-04-16",
      travelers: 2, total: "3190.00", budget: "4000.00" },
    { itinerary_id: 102, variant: "Bilanciata", city: "Tokyo", origin: "NAP", destination: "HND",
      hotel: "Hotel Sumida Riverside", hotel_stars: 4, start_date: "2027-04-10", end_date: "2027-04-16",
      travelers: 2, total: "3770.00", budget: "4000.00" },
    { itinerary_id: 103, variant: "Comfort", city: "Osaka", origin: "NAP", destination: "KIX",
      hotel: "Osaka Castle View", hotel_stars: 5, start_date: "2027-04-10", end_date: "2027-04-16",
      travelers: 2, total: "3980.00", budget: "4000.00" },
  ],
  [
    { itinerary_id: 201, variant: "Economica", city: "Tokyo", origin: "NAP", destination: "HND",
      hotel: "Ueno Garden Hotel", hotel_stars: 3, start_date: "2027-04-17", end_date: "2027-04-23",
      travelers: 2, total: "2980.00", budget: "4000.00" },
    { itinerary_id: 202, variant: "Bilanciata", city: "Tokyo", origin: "NAP", destination: "HND",
      hotel: "Shibuya Crossing Tower", hotel_stars: 4, start_date: "2027-04-17", end_date: "2027-04-23",
      travelers: 2, total: "3640.00", budget: "4000.00" },
  ],
];

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
    yield { event: "booking", data: { booking_id: 1, itinerary_id: pending.itinerary_id, status: "confirmed" } };
    yield* say(`Fatto: l'opzione ${pending.variant.toLowerCase()} è prenotata. La trovi in "Le mie prenotazioni".`);
    pending = null;
  } else if (/prenota/i.test(text) && proposalSet > 0) {
    const options = OPTIONS[proposalSet - 1];
    pending = options.find((o) => text.toLowerCase().includes(o.variant.toLowerCase())) ?? options[0];
    yield* say(
      `Riepilogo: ${pending.city}, opzione ${pending.variant.toLowerCase()}, hotel ${pending.hotel}, ` +
      `${pending.travelers} persone, ${Number(pending.total).toLocaleString("it-IT")} € in tutto. ` +
      "Confermi la prenotazione?",
    );
  } else {
    const index = Math.min(proposalSet, OPTIONS.length - 1);
    const supersedes = proposalSet > 0 ? `set-${proposalSet}` : null;
    yield { event: "requirements", data: { country: "Giappone", month: 4, nights: 6, travelers: 2,
      budget: "4000.00", origin: "NAP", preferences: ["cultura", "cibo"], missing: [] } };
    yield { event: "tool_start", data: { tool: "search_itineraries", label: "Cerco voli, hotel e attività" } };
    await wait(1200);
    yield { event: "tool_end", data: { tool: "search_itineraries" } };
    yield* say(supersedes
      ? "Spostando il viaggio di una settimana si risparmia qualcosa. Ecco le nuove opzioni."
      : "Ecco tre itinerari per il Giappone, dal 10 al 16 aprile, partendo da Napoli.");
    proposalSet = index + 1;
    yield { event: "itinerary", data: { proposal_set_id: `set-${proposalSet}`, supersedes, options: OPTIONS[index] } };
    yield* say("Apri i dettagli per vedere il programma giorno per giorno.");
  }
  yield { event: "done", data: { message_id: Date.now() } };
}