// Self-drive costs this much more than the vehicle's own with-driver rate - mirrors
// Booking.save()'s SELF_DRIVE_SURCHARGE_PERCENT on the backend, so any preview shown to a
// customer before submitting matches what actually gets charged.
export const SELF_DRIVE_SURCHARGE_PERCENT = 3

export function calculateTotalDays(startDate, endDate) {
  if (!startDate || !endDate) return 0
  const diff = (new Date(endDate) - new Date(startDate)) / (1000 * 60 * 60 * 24)
  return Math.max(1, Math.round(diff) + 1)
}

export function calculateEstimatedCost(pricePerDay, totalDays, serviceType) {
  const base = totalDays * Number(pricePerDay)
  if (serviceType !== 'self_drive') return base
  return Math.round(base * (1 + SELF_DRIVE_SURCHARGE_PERCENT / 100) * 100) / 100
}
