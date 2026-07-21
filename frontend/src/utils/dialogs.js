import Swal from 'sweetalert2'

// Matches this app's own navy/gold palette (see style.css's @theme block) so every dialog looks
// like part of the app rather than a generic default SweetAlert popup.
const BRAND = {
  background: '#0a1730', // navy-900
  color: '#e2e8f0', // slate-200
  confirmButtonColor: '#c9a227', // gold-500
  cancelButtonColor: '#16305c', // navy-700
}

// Drop-in async replacement for window.confirm() - await it the same way, just with `await`
// added since Swal is inherently a Promise (unlike the native, blocking confirm()).
export async function confirmDialog(text, { title, danger = false, confirmText = 'Yes', cancelText = 'Cancel' } = {}) {
  const result = await Swal.fire({
    icon: danger ? 'warning' : 'question',
    title,
    text,
    showCancelButton: true,
    confirmButtonText: confirmText,
    cancelButtonText: cancelText,
    ...BRAND,
    confirmButtonColor: danger ? '#dc2626' : BRAND.confirmButtonColor, // red-600 for destructive actions
  })
  return result.isConfirmed
}

// Drop-in async replacement for window.prompt() - returns the entered string, or null if
// cancelled (same contract as prompt() itself). inputType: 'password' masks the field, for
// re-confirming a password rather than free text (e.g. disabling 2FA).
export async function promptDialog(text, { title, defaultValue = '', placeholder = '', inputType = 'text' } = {}) {
  const result = await Swal.fire({
    title,
    text,
    input: inputType,
    inputValue: defaultValue,
    inputPlaceholder: placeholder,
    showCancelButton: true,
    confirmButtonText: 'OK',
    cancelButtonText: 'Cancel',
    ...BRAND,
  })
  return result.isConfirmed ? result.value : null
}
