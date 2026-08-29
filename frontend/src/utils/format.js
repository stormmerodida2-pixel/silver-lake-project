// Turns 1 -> "1st", 2 -> "2nd", 3 -> "3rd", 4 -> "4th", 11-13 -> "11th"/"12th"/"13th" (the
// standard English exceptions), 21 -> "21st", etc. - mirrors Django's own humanize `ordinal`
// filter, which the PDF receipt template uses for the same "this was your Nth trip" note.
export function ordinal(n) {
  const remainder100 = n % 100
  if (remainder100 >= 11 && remainder100 <= 13) return `${n}th`
  switch (n % 10) {
    case 1:
      return `${n}st`
    case 2:
      return `${n}nd`
    case 3:
      return `${n}rd`
    default:
      return `${n}th`
  }
}
