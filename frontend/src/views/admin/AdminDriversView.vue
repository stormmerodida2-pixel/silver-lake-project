<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import apiClient from '../../api/client'
import { confirmDialog } from '../../utils/dialogs'
import PhoneInput from '../../components/PhoneInput.vue'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const driverFilters = reactive({ search: '' })
const {
  items: drivers,
  nextUrl: driversNextUrl,
  loading: driversLoading,
  loadingMore: driversLoadingMore,
  error: driversError,
  load: loadDrivers,
  loadMore: loadMoreDrivers,
} = useAdminList('/admin/drivers/', driverFilters)

const {
  items: applications,
  nextUrl: applicationsNextUrl,
  loading: applicationsLoading,
  loadingMore: applicationsLoadingMore,
  error: applicationsError,
  load: loadApplications,
  loadMore: loadMoreApplications,
} = useAdminList('/admin/driver-applications/')

const {
  items: submissions,
  nextUrl: submissionsNextUrl,
  loading: submissionsLoading,
  loadingMore: submissionsLoadingMore,
  error: submissionsError,
  load: loadSubmissions,
  loadMore: loadMoreSubmissions,
} = useAdminList('/admin/vehicle-submissions/')

const busyId = ref(null)
const loading = computed(() => driversLoading.value || applicationsLoading.value || submissionsLoading.value)
const error = computed(() => driversError.value || applicationsError.value || submissionsError.value)

const pendingApplications = computed(() => applications.value.filter((a) => a.status === 'pending'))
const reviewedApplications = computed(() => applications.value.filter((a) => a.status !== 'pending'))

const pendingSubmissions = computed(() => submissions.value.filter((s) => s.status === 'pending'))
const reviewedSubmissions = computed(() => submissions.value.filter((s) => s.status !== 'pending'))

// ── Add-Driver modal ────────────────────────────────────────────────────────
const showModal = ref(false)
const saving = ref(false)
const formError = ref('')
const form = reactive({
  full_name: '',
  email: '',
  phone_number: '',
  years_of_experience: 0,
  bio: '',
})

function openModal() {
  Object.assign(form, { full_name: '', email: '', phone_number: '', years_of_experience: 0, bio: '' })
  formError.value = ''
  showModal.value = true
}

async function createDriver() {
  formError.value = ''
  if (!form.full_name.trim()) {
    formError.value = 'Full name is required.'
    return
  }
  saving.value = true
  try {
    const { data } = await apiClient.post('/admin/drivers/', {
      full_name: form.full_name,
      email: form.email,
      phone_number: form.phone_number,
      years_of_experience: Number(form.years_of_experience),
      bio: form.bio,
      is_active: true,
    })
    drivers.value.unshift(data)
    showModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    if (typeof detail === 'object') {
      formError.value = Object.values(detail).flat().join(' ')
    } else {
      formError.value = 'Could not create driver. Please try again.'
    }
  } finally {
    saving.value = false
  }
}

// ── Existing actions ─────────────────────────────────────────────────────────
async function activateDriver(driver) {
  busyId.value = driver.id
  try {
    const { data } = await apiClient.post(`/admin/drivers/${driver.id}/activate/`)
    Object.assign(driver, data)
  } catch {
    driversError.value = 'Could not update this driver.'
  } finally {
    busyId.value = null
  }
}

async function toggleCashPayments(driver) {
  busyId.value = driver.id
  try {
    const { data } = await apiClient.patch(`/admin/drivers/${driver.id}/`, {
      cash_payments_enabled: !driver.cash_payments_enabled,
    })
    Object.assign(driver, data)
  } catch {
    driversError.value = 'Could not update this driver.'
  } finally {
    busyId.value = null
  }
}

// ── Suspend-with-reason modal ────────────────────────────────────────────────
const showSuspendModal = ref(false)
const suspendingDriver = ref(null)
const suspendReason = ref('')
const suspending = ref(false)

function openSuspendModal(driver) {
  suspendingDriver.value = driver
  suspendReason.value = ''
  showSuspendModal.value = true
}

// ── Edit-license modal ───────────────────────────────────────────────────────
const showLicenseModal = ref(false)
const editingLicenseDriver = ref(null)
const licenseForm = reactive({ license_number: '', license_expiry_date: '' })
const savingLicense = ref(false)

function openLicenseModal(driver) {
  editingLicenseDriver.value = driver
  Object.assign(licenseForm, {
    license_number: driver.license_number || '',
    license_expiry_date: driver.license_expiry_date || '',
  })
  showLicenseModal.value = true
}

async function saveLicense() {
  savingLicense.value = true
  busyId.value = editingLicenseDriver.value.id
  try {
    const { data } = await apiClient.patch(`/admin/drivers/${editingLicenseDriver.value.id}/`, {
      license_number: licenseForm.license_number,
      license_expiry_date: licenseForm.license_expiry_date || null,
    })
    Object.assign(editingLicenseDriver.value, data)
    showLicenseModal.value = false
  } catch {
    driversError.value = 'Could not update this license.'
  } finally {
    savingLicense.value = false
    busyId.value = null
  }
}

async function confirmSuspend() {
  if (!suspendReason.value.trim()) return
  suspending.value = true
  busyId.value = suspendingDriver.value.id
  try {
    const { data } = await apiClient.post(`/admin/drivers/${suspendingDriver.value.id}/suspend/`, {
      reason: suspendReason.value.trim(),
    })
    Object.assign(suspendingDriver.value, data)
    showSuspendModal.value = false
  } catch {
    driversError.value = 'Could not suspend this driver.'
  } finally {
    suspending.value = false
    busyId.value = null
  }
}

async function inviteDriver(driver) {
  busyId.value = driver.id
  try {
    const { data } = await apiClient.post(`/admin/drivers/${driver.id}/invite/`)
    Object.assign(driver, data)
  } catch (err) {
    driversError.value = err?.response?.data?.detail || 'Could not send portal invite.'
  } finally {
    busyId.value = null
  }
}

async function impersonate(driver) {
  if (
    !(await confirmDialog(
      `View the app as ${driver.full_name}'s driver portal? You'll act as this driver until you stop impersonating.`,
    ))
  )
    return
  busyId.value = driver.id
  try {
    await auth.startImpersonation(driver.user_id, route.fullPath)
    router.push('/driver')
  } catch {
    driversError.value = 'Could not start impersonating this driver.'
  } finally {
    busyId.value = null
  }
}

async function deleteDriver(driver) {
  if (!(await confirmDialog(`Delete ${driver.full_name}? This cannot be undone.`, { danger: true }))) return
  busyId.value = driver.id
  try {
    await apiClient.delete(`/admin/drivers/${driver.id}/`)
    drivers.value = drivers.value.filter((d) => d.id !== driver.id)
  } catch (err) {
    driversError.value = err.response?.data?.detail || 'Could not delete this driver.'
  } finally {
    busyId.value = null
  }
}

async function approveApplication(application) {
  busyId.value = application.id
  try {
    const { data } = await apiClient.post(`/admin/driver-applications/${application.id}/approve/`)
    Object.assign(application, data)
    await loadDrivers()
  } catch {
    applicationsError.value = 'Could not approve this application.'
  } finally {
    busyId.value = null
  }
}

async function rejectApplication(application) {
  busyId.value = application.id
  try {
    const { data } = await apiClient.post(`/admin/driver-applications/${application.id}/reject/`)
    Object.assign(application, data)
  } catch {
    applicationsError.value = 'Could not reject this application.'
  } finally {
    busyId.value = null
  }
}

async function approveSubmission(submission) {
  busyId.value = submission.id
  try {
    const { data } = await apiClient.post(`/admin/vehicle-submissions/${submission.id}/approve/`)
    Object.assign(submission, data)
  } catch {
    submissionsError.value = 'Could not approve this vehicle.'
  } finally {
    busyId.value = null
  }
}

async function rejectSubmission(submission) {
  busyId.value = submission.id
  try {
    const { data } = await apiClient.post(`/admin/vehicle-submissions/${submission.id}/reject/`)
    Object.assign(submission, data)
  } catch {
    submissionsError.value = 'Could not reject this vehicle.'
  } finally {
    busyId.value = null
  }
}

onMounted(() => {
  loadDrivers()
  loadApplications()
  loadSubmissions()
})
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between">
      <h1 class="font-[Georgia] text-2xl font-bold text-foreground">Manage Drivers</h1>
      <button
        v-if="auth.user?.is_superuser"
        id="add-driver-btn"
        class="flex items-center gap-2 rounded-lg bg-accent-bg px-4 py-2 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-bg-hover"
        @click="openModal"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        Add Driver
      </button>
    </div>

    <p v-if="loading" class="mt-10 text-center text-foreground-muted">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-danger">{{ error }}</p>

    <template v-if="!loading">
      <section class="mt-8">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-accent">
          Pending Applications ({{ pendingApplications.length }})
        </h2>
        <div class="mt-3 space-y-4">
          <div
            v-for="application in pendingApplications"
            :key="application.id"
            class="rounded-xl border border-accent-border-strong bg-surface p-5"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 class="font-[Georgia] text-lg font-bold text-foreground">{{ application.full_name }}</h3>
                <p class="text-sm text-foreground-muted">{{ application.email }} - {{ application.phone_number }}</p>
                <p class="text-sm text-foreground-muted">
                  {{ application.years_of_experience }} years experience - License #{{ application.license_number }}
                </p>
                <p class="mt-1 text-sm text-foreground-secondary">
                  Vehicle: {{ application.vehicle_name }} ({{
                    application.vehicle_category_name || application.vehicle_category
                  }}), {{ application.passenger_capacity }} pax, KES
                  {{ Number(application.price_per_day).toLocaleString() }}/day
                </p>
                <div class="mt-2 flex flex-wrap gap-3 text-sm">
                  <a :href="application.license_document" target="_blank" class="text-accent hover:text-accent-strong">
                    License Document
                  </a>
                  <a
                    v-if="application.vehicle_photo"
                    :href="application.vehicle_photo"
                    target="_blank"
                    class="text-accent hover:text-accent-strong"
                  >
                    Vehicle Photo
                  </a>
                  <a
                    v-if="application.vehicle_logbook_document"
                    :href="application.vehicle_logbook_document"
                    target="_blank"
                    class="text-accent hover:text-accent-strong"
                  >
                    Logbook
                  </a>
                </div>
              </div>
              <div class="flex gap-2">
                <button
                  :disabled="busyId === application.id"
                  class="rounded-md bg-accent-bg px-3 py-1.5 text-sm font-semibold text-on-accent hover:bg-accent-bg-hover disabled:opacity-50"
                  @click="approveApplication(application)"
                >
                  Approve
                </button>
                <button
                  :disabled="busyId === application.id"
                  class="rounded-md border border-danger-border px-3 py-1.5 text-sm font-semibold text-danger hover:bg-red-400 hover:text-on-accent disabled:opacity-50"
                  @click="rejectApplication(application)"
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
          <p v-if="!pendingApplications.length" class="text-sm text-foreground-muted">No pending applications.</p>
          <div v-if="applicationsNextUrl" class="text-center">
            <button
              :disabled="applicationsLoadingMore"
              class="rounded-md border border-border px-4 py-1.5 text-sm font-medium text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
              @click="loadMoreApplications"
            >
              {{ applicationsLoadingMore ? 'Loading...' : 'Load More Applications' }}
            </button>
          </div>
        </div>
      </section>

      <section class="mt-10">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-accent">
          Pending Vehicle Submissions ({{ pendingSubmissions.length }})
        </h2>
        <p class="mt-1 text-xs text-foreground-subtle">Cars drivers have submitted themselves via the driver portal.</p>
        <div class="mt-3 space-y-4">
          <div
            v-for="submission in pendingSubmissions"
            :key="submission.id"
            class="rounded-xl border border-accent-border-strong bg-surface p-5"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 class="font-[Georgia] text-lg font-bold text-foreground">{{ submission.name }}</h3>
                <p class="text-sm text-foreground-muted">Submitted by {{ submission.driver_name }}</p>
                <p class="mt-1 text-sm text-foreground-secondary">
                  {{ submission.category_name || submission.category }}, {{ submission.passenger_capacity }} pax, KES
                  {{ Number(submission.price_per_day).toLocaleString() }}/day
                </p>
                <div v-if="submission.photos?.length" class="mt-2 flex flex-wrap gap-2">
                  <a v-for="photo in submission.photos" :key="photo.id" :href="photo.image" target="_blank">
                    <img :src="photo.image" alt="" class="h-16 w-24 rounded-lg border border-border-subtle object-cover" />
                  </a>
                </div>
                <div class="mt-2 flex flex-wrap gap-3 text-sm">
                  <a :href="submission.logbook_document" target="_blank" class="text-accent hover:text-accent-strong">
                    Logbook
                  </a>
                </div>
              </div>
              <div class="flex gap-2">
                <button
                  :disabled="busyId === submission.id"
                  class="rounded-md bg-accent-bg px-3 py-1.5 text-sm font-semibold text-on-accent hover:bg-accent-bg-hover disabled:opacity-50"
                  @click="approveSubmission(submission)"
                >
                  Approve
                </button>
                <button
                  :disabled="busyId === submission.id"
                  class="rounded-md border border-danger-border px-3 py-1.5 text-sm font-semibold text-danger hover:bg-red-400 hover:text-on-accent disabled:opacity-50"
                  @click="rejectSubmission(submission)"
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
          <p v-if="!pendingSubmissions.length" class="text-sm text-foreground-muted">No pending vehicle submissions.</p>
          <div v-if="submissionsNextUrl" class="text-center">
            <button
              :disabled="submissionsLoadingMore"
              class="rounded-md border border-border px-4 py-1.5 text-sm font-medium text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
              @click="loadMoreSubmissions"
            >
              {{ submissionsLoadingMore ? 'Loading...' : 'Load More Submissions' }}
            </button>
          </div>
        </div>
      </section>

      <section class="mt-10">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-accent">Live Drivers</h2>
        <input
          v-model="driverFilters.search"
          type="text"
          placeholder="Search by name, email or phone..."
          class="mt-3 w-full max-w-sm rounded-md border border-border bg-page px-3 py-2 text-sm text-foreground placeholder:text-foreground-subtle focus:border-accent-border focus:outline-none"
        />
        <div class="mt-3 overflow-x-auto rounded-xl border border-border-subtle">
          <table class="w-full text-left text-sm">
            <thead class="bg-surface text-foreground-muted">
              <tr>
                <th class="px-4 py-3">Name</th>
                <th class="px-4 py-3">Email</th>
                <th class="px-4 py-3">Phone</th>
                <th class="px-4 py-3">Experience</th>
                <th class="px-4 py-3">Rating</th>
                <th class="px-4 py-3">License</th>
                <th class="px-4 py-3">Status</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-border-subtle bg-page">
              <tr v-for="driver in drivers" :key="driver.id">
                <td class="px-4 py-3 text-foreground">{{ driver.full_name }}</td>
                <td class="px-4 py-3 text-foreground-secondary">{{ driver.email || '-' }}</td>
                <td class="px-4 py-3 text-foreground-secondary">{{ driver.phone_number || '-' }}</td>
                <td class="px-4 py-3 text-foreground-secondary">{{ driver.years_of_experience }} yrs</td>
                <td class="px-4 py-3 text-foreground-secondary">{{ Number(driver.rating).toFixed(1) }}</td>
                <td class="px-4 py-3 text-xs">
                  <span v-if="!driver.license_expiry_date" class="text-foreground-subtle">Not set</span>
                  <span
                    v-else
                    :class="driver.is_license_expired ? 'font-bold text-danger' : 'text-foreground-secondary'"
                  >
                    {{ driver.license_expiry_date }}
                    <span v-if="driver.is_license_expired" class="ml-1">⚠ Expired</span>
                  </span>
                </td>
                <td class="px-4 py-3">
                  <div class="flex flex-col gap-1">
                    <span
                      class="inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold"
                      :class="driver.is_active ? 'bg-emerald-500/10 text-success' : 'bg-red-500/10 text-danger'"
                    >
                      <span
                        class="h-1.5 w-1.5 rounded-full"
                        :class="driver.is_active ? 'bg-emerald-400' : 'bg-red-400'"
                      />
                      {{ driver.is_active ? 'Active' : 'Suspended' }}
                    </span>
                    <span
                      v-if="driver.is_active && driver.is_away"
                      class="inline-flex w-fit items-center gap-1.5 rounded-full bg-surface-2 px-2.5 py-0.5 text-xs font-semibold text-foreground-secondary"
                      :title="driver.away_reason"
                    >
                      Away
                    </span>
                    <span
                      v-if="!driver.is_active && driver.suspension_reason"
                      class="max-w-[180px] text-xs text-foreground-subtle"
                    >
                      {{ driver.suspension_reason }}
                    </span>
                    <span
                      v-if="!driver.cash_payments_enabled"
                      class="inline-flex w-fit items-center gap-1.5 rounded-full bg-red-500/10 px-2.5 py-0.5 text-xs font-semibold text-danger"
                      title="This driver can only be paid via card or bank transfer (M-Pesa's own STK push is temporarily disabled platform-wide) - cash is disabled."
                    >
                      Cash Disabled
                    </span>
                  </div>
                </td>
                <td class="space-x-2 whitespace-nowrap px-4 py-3">
                  <button
                    v-if="auth.user?.is_superuser"
                    :disabled="busyId === driver.id"
                    class="rounded-md border border-border px-2 py-1 text-xs font-semibold text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
                    @click="openLicenseModal(driver)"
                  >
                    Edit License
                  </button>
                  <button
                    v-if="driver.is_active"
                    :disabled="busyId === driver.id"
                    class="rounded-md border border-border px-2 py-1 text-xs font-semibold text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
                    @click="openSuspendModal(driver)"
                  >
                    Suspend
                  </button>
                  <button
                    v-else
                    :disabled="busyId === driver.id"
                    class="rounded-md border border-border px-2 py-1 text-xs font-semibold text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
                    @click="activateDriver(driver)"
                  >
                    Activate
                  </button>
                  <button
                    v-if="auth.user?.is_superuser"
                    :disabled="busyId === driver.id"
                    class="rounded-md border border-border px-2 py-1 text-xs font-semibold text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
                    @click="toggleCashPayments(driver)"
                  >
                    {{ driver.cash_payments_enabled ? 'Disable Cash' : 'Enable Cash' }}
                  </button>
                  <button
                    v-if="driver.email && !driver.has_portal_account"
                    :disabled="busyId === driver.id"
                    class="rounded-md border border-border px-2 py-1 text-xs font-semibold text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
                    @click="inviteDriver(driver)"
                  >
                    Send Invite
                  </button>
                  <button
                    v-if="auth.user?.is_superuser && !auth.user?.organization_name && driver.has_portal_account"
                    :disabled="busyId === driver.id"
                    title="View the driver portal as this driver, for support/debugging"
                    class="rounded-md border border-border px-2 py-1 text-xs font-semibold text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
                    @click="impersonate(driver)"
                  >
                    Impersonate
                  </button>
                  <button
                    v-if="auth.user?.is_superuser"
                    :disabled="busyId === driver.id"
                    class="rounded-md border border-danger-border px-2 py-1 text-xs font-semibold text-danger hover:bg-red-400 hover:text-on-accent disabled:opacity-50"
                    @click="deleteDriver(driver)"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-if="!drivers.length" class="p-6 text-center text-foreground-muted">No drivers yet.</p>
          <div v-if="driversNextUrl" class="border-t border-border-subtle p-3 text-center">
            <button
              :disabled="driversLoadingMore"
              class="rounded-md border border-border px-4 py-1.5 text-sm font-medium text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
              @click="loadMoreDrivers"
            >
              {{ driversLoadingMore ? 'Loading...' : 'Load More' }}
            </button>
          </div>
        </div>
      </section>

      <section v-if="reviewedApplications.length" class="mt-10">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-accent">Reviewed Applications</h2>
        <div class="mt-3 space-y-2">
          <div
            v-for="application in reviewedApplications"
            :key="application.id"
            class="flex items-center justify-between rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm"
          >
            <span class="text-foreground-secondary">{{ application.full_name }} - {{ application.vehicle_name }}</span>
            <span :class="application.status === 'approved' ? 'text-accent' : 'text-danger'">
              {{ application.status }}
            </span>
          </div>
        </div>
      </section>

      <section v-if="reviewedSubmissions.length" class="mt-10">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-accent">Reviewed Vehicle Submissions</h2>
        <div class="mt-3 space-y-2">
          <div
            v-for="submission in reviewedSubmissions"
            :key="submission.id"
            class="flex items-center justify-between rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm"
          >
            <span class="text-foreground-secondary">{{ submission.name }} - {{ submission.driver_name }}</span>
            <span :class="submission.status === 'approved' ? 'text-accent' : 'text-danger'">
              {{ submission.status }}
            </span>
          </div>
        </div>
      </section>
    </template>

    <!-- Add Driver Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showModal"
          id="add-driver-modal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showModal = false"
        >
          <div class="w-full max-w-md rounded-2xl border border-border bg-surface p-8 shadow-2xl">
            <!-- Modal header -->
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-foreground">Add New Driver</h2>
              <button class="text-foreground-muted transition-colors hover:text-foreground" @click="showModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <!-- Error -->
            <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-danger">
              {{ formError }}
            </p>

            <!-- Form -->
            <form class="space-y-4" @submit.prevent="createDriver">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted">Full Name *</label>
                <input
                  id="new-driver-full-name"
                  v-model="form.full_name"
                  type="text"
                  placeholder="John Kamau"
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground placeholder-foreground-subtle focus:border-accent-border-strong focus:outline-none focus:ring-1 focus:ring-accent-border-strong"
                  required
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted">Email</label>
                <input
                  id="new-driver-email"
                  v-model="form.email"
                  type="email"
                  placeholder="john@example.com"
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground placeholder-foreground-subtle focus:border-accent-border-strong focus:outline-none focus:ring-1 focus:ring-accent-border-strong"
                />
                <p class="mt-1 text-xs text-foreground-subtle">Used to notify the driver when they're booked.</p>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                  >Phone Number</label
                >
                <PhoneInput v-model="form.phone_number" />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                  >Years of Experience</label
                >
                <input
                  id="new-driver-experience"
                  v-model="form.years_of_experience"
                  type="number"
                  min="0"
                  max="50"
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground placeholder-foreground-subtle focus:border-accent-border-strong focus:outline-none focus:ring-1 focus:ring-accent-border-strong"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                  >Bio / Description</label
                >
                <textarea
                  id="new-driver-bio"
                  v-model="form.bio"
                  rows="3"
                  placeholder="Brief driver bio…"
                  class="w-full resize-none rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground placeholder-foreground-subtle focus:border-accent-border-strong focus:outline-none focus:ring-1 focus:ring-accent-border-strong"
                />
              </div>

              <p class="text-xs text-foreground-subtle">
                The driver will be set to <span class="text-accent">Active</span> immediately and appear in the live
                drivers list.
              </p>

              <div class="flex gap-3 pt-2">
                <button
                  type="button"
                  class="flex-1 rounded-lg border border-border py-2.5 text-sm font-semibold text-foreground-secondary transition-colors hover:border-slate-500 hover:text-foreground"
                  @click="showModal = false"
                >
                  Cancel
                </button>
                <button
                  id="create-driver-submit"
                  type="submit"
                  :disabled="saving"
                  class="flex-1 rounded-lg bg-accent-bg py-2.5 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-bg-hover disabled:opacity-50"
                >
                  {{ saving ? 'Creating…' : 'Create Driver' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Suspend Driver Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showSuspendModal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showSuspendModal = false"
        >
          <div class="w-full max-w-md rounded-2xl border border-border bg-surface p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-foreground">Suspend {{ suspendingDriver?.full_name }}</h2>
              <button class="text-foreground-muted transition-colors hover:text-foreground" @click="showSuspendModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p class="mb-4 text-sm text-foreground-muted">
              This reason will be emailed to the driver and shown here to other admins.
            </p>

            <form class="space-y-4" @submit.prevent="confirmSuspend">
              <textarea
                v-model="suspendReason"
                rows="3"
                required
                placeholder="e.g. Repeated customer complaints about late pickups"
                class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground placeholder-foreground-subtle focus:border-accent-border-strong focus:outline-none focus:ring-1 focus:ring-accent-border-strong"
              ></textarea>

              <div class="flex gap-3 pt-2">
                <button
                  type="button"
                  class="flex-1 rounded-lg border border-border py-2.5 text-sm font-semibold text-foreground-secondary transition-colors hover:border-slate-500 hover:text-foreground"
                  @click="showSuspendModal = false"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  :disabled="suspending || !suspendReason.trim()"
                  class="flex-1 rounded-lg bg-red-500 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-red-400 disabled:opacity-50"
                >
                  {{ suspending ? 'Suspending…' : 'Confirm Suspend' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Edit License Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showLicenseModal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showLicenseModal = false"
        >
          <div class="w-full max-w-md rounded-2xl border border-border bg-surface p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-foreground">
                Edit License — {{ editingLicenseDriver?.full_name }}
              </h2>
              <button class="text-foreground-muted transition-colors hover:text-foreground" @click="showLicenseModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p class="mb-4 text-sm text-foreground-muted">
              Setting an expiry date warns this driver (and staff) before it lapses, and again the
              day it does - once expired, their vehicle(s) are automatically hidden from the public
              site until it's renewed here.
            </p>

            <form class="space-y-4" @submit.prevent="saveLicense">
              <div>
                <label class="mb-1 block text-xs text-foreground-muted">License Number</label>
                <input
                  v-model="licenseForm.license_number"
                  type="text"
                  placeholder="DL123456"
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground placeholder-foreground-subtle focus:border-accent-border-strong focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs text-foreground-muted">License Expiry</label>
                <input
                  v-model="licenseForm.license_expiry_date"
                  type="date"
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground focus:border-accent-border-strong focus:outline-none"
                />
              </div>

              <div class="flex gap-3 pt-2">
                <button
                  type="button"
                  class="flex-1 rounded-lg border border-border py-2.5 text-sm font-semibold text-foreground-secondary transition-colors hover:border-slate-500 hover:text-foreground"
                  @click="showLicenseModal = false"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  :disabled="savingLicense"
                  class="flex-1 rounded-lg bg-accent-bg py-2.5 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-bg-hover disabled:opacity-50"
                >
                  {{ savingLicense ? 'Saving…' : 'Save' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
