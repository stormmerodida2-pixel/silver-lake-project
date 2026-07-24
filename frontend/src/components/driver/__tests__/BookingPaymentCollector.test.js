import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../api/client', () => ({
  default: { post: vi.fn() },
}))

import { useDriverPortalStore } from '../../../stores/driverPortal'
import BookingPaymentCollector from '../BookingPaymentCollector.vue'

function makeBooking(overrides = {}) {
  return {
    id: 1,
    balance_due: '3500.00',
    pending_payments: [],
    ...overrides,
  }
}

async function mountAndOpenForm(booking, cashPaymentsEnabled = true) {
  setActivePinia(createPinia())
  const driverPortal = useDriverPortalStore()
  driverPortal.profile = { cash_payments_enabled: cashPaymentsEnabled }

  const wrapper = mount(BookingPaymentCollector, { props: { booking } })
  await wrapper.find('button').trigger('click') // "+ Collect Payment"
  return wrapper
}

describe('BookingPaymentCollector payment method options', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers cash, card, and bank transfer when the driver is cash-enabled', async () => {
    const wrapper = await mountAndOpenForm(makeBooking(), true)

    const labels = wrapper.findAll('button').map((b) => b.text())
    expect(labels).toContain('cash')
    expect(labels).toContain('card')
    expect(labels).toContain('Bank Transfer')
    // M-Pesa is intentionally disabled (MPESA_ENABLED = false) until real production
    // credentials are in place - see the component's own comment.
    expect(labels).not.toContain('M-Pesa')
  })

  it('omits cash entirely when the driver has cash payments disabled', async () => {
    const wrapper = await mountAndOpenForm(makeBooking(), false)

    const labels = wrapper.findAll('button').map((b) => b.text())
    expect(labels).not.toContain('cash')
    expect(labels).toContain('card')
    expect(labels).toContain('Bank Transfer')
    expect(wrapper.text()).toContain('Cash payments are disabled for your account')
  })

  it('defaults the payment method draft to card when cash is disabled', async () => {
    const wrapper = await mountAndOpenForm(makeBooking(), false)

    const cardButton = wrapper.findAll('button').find((b) => b.text() === 'card')
    expect(cardButton.classes()).toContain('border-gold-500')
  })

  it('does not offer to collect payment at all once the balance is fully paid', async () => {
    setActivePinia(createPinia())
    const driverPortal = useDriverPortalStore()
    driverPortal.profile = { cash_payments_enabled: true }

    const wrapper = mount(BookingPaymentCollector, { props: { booking: makeBooking({ balance_due: '0.00' }) } })

    expect(wrapper.text()).not.toContain('Collect Payment')
  })

  it('hides the "Confirm Received" button for a pending bank-transfer payment (staff-only)', async () => {
    setActivePinia(createPinia())
    const driverPortal = useDriverPortalStore()
    driverPortal.profile = { cash_payments_enabled: true }
    const booking = makeBooking({
      pending_payments: [{ id: 5, method: 'bank_transfer', amount: '1000.00', note: 'REF1234' }],
    })

    const wrapper = mount(BookingPaymentCollector, { props: { booking } })

    expect(wrapper.text()).toContain('awaiting confirmation from our team')
    expect(wrapper.text()).not.toContain('Confirm Received')
  })

  it('shows "Confirm Received" for a pending cash payment (driver-confirmable)', async () => {
    setActivePinia(createPinia())
    const driverPortal = useDriverPortalStore()
    driverPortal.profile = { cash_payments_enabled: true }
    const booking = makeBooking({
      pending_payments: [{ id: 5, method: 'cash', amount: '1000.00', note: '' }],
    })

    const wrapper = mount(BookingPaymentCollector, { props: { booking } })

    expect(wrapper.text()).toContain('Confirm Received')
  })
})
