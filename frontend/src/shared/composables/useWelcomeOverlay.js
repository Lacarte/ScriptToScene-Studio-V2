import { ref } from 'vue'

const quotes = [
  '"Simplicity is the ultimate sophistication." - Leonardo da Vinci',
  '"Creativity is intelligence having fun." - Albert Einstein',
  '"The details are not the details. They make the design." - Charles Eames',
  '"What we think, we become." - Buddha',
  '"Discipline is choosing between what you want now and what you want most." - Abraham Lincoln',
  '"The obstacle is the way." - Marcus Aurelius',
  '"Life shrinks or expands in proportion to one\'s courage." - Anais Nin',
  '"The unexamined life is not worth living." - Socrates',
]

const isVisible = ref(false)
const isDismissing = ref(false)
const quote = ref(quotes[0])

let dismissTimer = null

function pickQuote() {
  quote.value = quotes[Math.floor(Math.random() * quotes.length)]
}

function clearDismissTimer() {
  if (dismissTimer) {
    clearTimeout(dismissTimer)
    dismissTimer = null
  }
}

function showWelcome({ force = false } = {}) {
  if (!force && localStorage.getItem('sts-welcome-seen')) return
  clearDismissTimer()
  pickQuote()
  isDismissing.value = false
  isVisible.value = true
}

function dismissWelcome() {
  if (!isVisible.value) return
  localStorage.setItem('sts-welcome-seen', '1')
  isDismissing.value = true
  clearDismissTimer()
  dismissTimer = setTimeout(() => {
    isVisible.value = false
    isDismissing.value = false
    dismissTimer = null
  }, 800)
}

function replayWelcome() {
  localStorage.removeItem('sts-welcome-seen')
  showWelcome({ force: true })
}

function initWelcome() {
  if (!localStorage.getItem('sts-welcome-seen')) {
    showWelcome()
  }
}

export function useWelcomeOverlay() {
  return {
    isVisible,
    isDismissing,
    quote,
    initWelcome,
    showWelcome,
    dismissWelcome,
    replayWelcome,
  }
}
