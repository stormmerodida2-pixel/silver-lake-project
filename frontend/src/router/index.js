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
    path: '/admin',
    component: () => import('../layouts/AdminLayout.vue'),
    meta: { requiresStaff: true },
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
    ],
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
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title || 'SilverLake Car Rentals'
})

export default router
