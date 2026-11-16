// Formatting shared by the pages: euros and dates in Italian.

// Italian skips the thousands separator below 10.000 ("3640 €"): "always" gives "3.640 €"
const euroFormat = new Intl.NumberFormat("it-IT", {
  style: "currency", currency: "EUR", maximumFractionDigits: 0, useGrouping: "always",
});
const shortFormat = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long" });
const monthFormat = new Intl.DateTimeFormat("it-IT", { month: "long" });

// amounts arrive from the API as strings ("3770.00"): Decimal on the server, never float
export const euro = (amount) => euroFormat.format(Number(amount));

// "2027-04-10" is read as a local date, not as midnight UTC
const toDate = (iso) => new Date(`${iso}T00:00:00`);

export function dateRange(startIso, endIso) {
  const start = toDate(startIso);
  const end = toDate(endIso);
  return start.getMonth() === end.getMonth()
    ? `${start.getDate()}–${shortFormat.format(end)}`
    : `${shortFormat.format(start)} – ${shortFormat.format(end)}`;
}

export const monthName = (month) => monthFormat.format(new Date(2000, month - 1, 1));