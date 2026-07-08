import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/',
    name: 'home',
    component: () => import('../views/HomeView.vue'),
    meta: { title: 'SilverLake Car Rentals | Car Hire in Kisumu & Across Kenya' },
  },
  {
    path: '/fleet',
    name: 'fleet',
    component: () => import('../views/FleetView.vue'),
    meta: { title: 'Our Fleet | SilverLake Car Rentals' },
  },
  {
    path: '/fleet/:id',
    name: 'vehicle-detail',
    component: () => import('../views/VehicleDetailView.vue'),
    meta: { title: 'Vehicle Details | SilverLake Car Rentals' },
  },
  {
    path: '/drivers',
    name: 'drivers',
    component: () => import('../views/DriversView.vue'),
    meta: { title: 'Our Drivers | SilverLake Car Rentals' },
  },
  {
    path: '/reviews',
    name: 'reviews',
    component: () => import('../views/ReviewsView.vue'),
    meta: { title: 'Customer Reviews | SilverLake Car Rentals' },
  },
  {
    path: '/contact',
    name: 'contact',
    component: () => import('../views/ContactView.vue'),
    meta: { title: 'Contact Us | SilverLake Car Rentals' },
  },
  {
    path: '/terms',
    name: 'terms',
    component: () => import('../views/legal/TermsView.vue'),
    meta: { title: 'Terms of Service | SilverLake Car Rentals' },
  },
  {
    path: '/privacy',
    name: 'privacy',
    component: () => import('../views/legal/PrivacyView.vue'),
    meta: { title: 'Privacy Policy | SilverLake Car Rentals' },
  },
  {
    path: '/refund-policy',
    name: 'refund-policy',
    component: () => import('../views/legal/RefundPolicyView.vue'),
    meta: { title: 'Refund & Cancellation Policy | SilverLake Car Rentals' },
  },
  {
    path: '/book',
    name: 'book',
    component: () => import('../views/BookingView.vue'),
    meta: { title: 'Book Your Ride | SilverLake Car Rentals', requiresAuth: true },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { title: 'Log In | SilverLake Car Rentals' },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('../views/RegisterView.vue'),
    meta: { title: 'Sign Up | SilverLake Car Rentals' },
  },
  {
    path: '/activate/:uid/:token',
    name: 'activate',
    component: () => import('../views/ActivateAccountView.vue'),
    meta: { title: 'Activate Account | SilverLake Car Rentals' },
  },
  {
    path: '/forgot-password',
    name: 'forgot-password',
    component: () => import('../views/ForgotPasswordView.vue'),
    meta: { title: 'Forgot Password | SilverLake Car Rentals' },
  },
  {
    path: '/reset-password/:uid/:token',
    name: 'reset-password',
    component: () => import('../views/ResetPasswordView.vue'),
    meta: { title: 'Reset Password | SilverLake Car Rentals' },
  },
  {
    path: '/account/profile',
    name: 'profile',
    component: () => import('../views/ProfileView.vue'),
    meta: { title: 'My Profile | SilverLake Car Rentals', requiresAuth: true },
  },
  {
    path: '/account/change-password',
    name: 'change-password',
    component: () => import('../views/ChangePasswordView.vue'),
    meta: { title: 'Change Password | SilverLake Car Rentals', requiresAuth: true },
  },
  {
    path: '/account/bookings',
    name: 'my-bookings',
    component: () => import('../views/MyBookingsView.vue'),
    meta: { title: 'My Bookings | SilverLake Car Rentals', requiresAuth: true },
  },
  {
    path: '/become-a-driver',
    name: 'become-a-driver',
    component: () => import('../views/BecomeDriverView.vue'),
    meta: { title: 'Become a Driver | SilverLake Car Rentals' },
  },
  {
    path: '/driver/booking/:token',
    name: 'driver-booking',
    component: () => import('../views/DriverBookingView.vue'),
    meta: { title: 'Complete Booking | SilverLake Driver Portal' },
  },
  {
    path: '/pay/:token',
    name: 'pay-booking',
    component: () => import('../views/PayBookingView.vue'),
    meta: { title: 'Pay for Your Trip | SilverLake Car Rentals' },
  },
  {
    path: '/driver',
    name: 'driver-portal',
    component: () => import('../views/driver/DriverPortalView.vue'),
    meta: { title: 'Driver Portal | SilverLake Car Rentals', requiresDriver: true, hideChrome: true },
  },
  {
    path: '/admin',
    component: () => import('../layouts/AdminLayout.vue'),
    meta: { requiresStaff: true, hideChrome: true },
    children: [
      {
        path: '',
        name: 'admin-dashboard',
        component: () => import('../views/admin/AdminDashboardView.vue'),
        meta: { title: 'Admin Dashboard | SilverLake Car Rentals', pageTitle: 'Dashboard' },
      },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('../views/admin/AdminUsersView.vue'),
        meta: { title: 'Manage Users | SilverLake Car Rentals', pageTitle: 'Users' },
      },
      {
        path: 'bookings',
        name: 'admin-bookings',
        component: () => import('../views/admin/AdminBookingsView.vue'),
        meta: { title: 'Manage Bookings | SilverLake Car Rentals', pageTitle: 'Bookings' },
      },
      {
        path: 'fleet',
        name: 'admin-fleet',
        component: () => import('../views/admin/AdminFleetView.vue'),
        meta: { title: 'Manage Fleet | SilverLake Car Rentals', pageTitle: 'Fleet' },
      },
      {
        path: 'drivers',
        name: 'admin-drivers',
        component: () => import('../views/admin/AdminDriversView.vue'),
        meta: { title: 'Manage Drivers | SilverLake Car Rentals', pageTitle: 'Drivers' },
      },
      {
        path: 'reviews',
        name: 'admin-reviews',
        component: () => import('../views/admin/AdminReviewsView.vue'),
        meta: { title: 'Review Moderation | SilverLake Car Rentals', pageTitle: 'Reviews' },
      },
      {
        path: 'payouts',
        name: 'admin-payouts',
        component: () => import('../views/admin/AdminPayoutsView.vue'),
        meta: { title: 'Driver Payouts | SilverLake Car Rentals', pageTitle: 'Payouts' },
      },
      {
        path: 'refunds',
        name: 'admin-refunds',
        component: () => import('../views/admin/AdminRefundsView.vue'),
        meta: { title: 'Refunds | SilverLake Car Rentals', pageTitle: 'Refunds' },
      },
      {
        path: 'payments',
        name: 'admin-payments',
        component: () => import('../views/admin/AdminPaymentsView.vue'),
        meta: { title: 'Payments | SilverLake Car Rentals', pageTitle: 'Payments' },
      },
      {
        path: 'audit-log',
        name: 'admin-audit-log',
        component: () => import('../views/admin/AdminAuditLogView.vue'),
        meta: { title: 'Activity Log | SilverLake Car Rentals', pageTitle: 'Activity Log' },
      },
    ],
  },
  // Catch-all 404
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('../views/NotFoundView.vue'),
    meta: { title: '404 Not Found | SilverLake Car Rentals' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.requiresStaff) {
    if (!auth.isAuthenticated) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    if (!auth.user?.is_staff) {
      return { name: 'home' }
    }
  }
  if (to.meta.requiresDriver) {
    if (!auth.isAuthenticated) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    if (!auth.user?.is_driver) {
      return { name: 'home' }
    }
  }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title || 'SilverLake Car Rentals'
})

export default router
