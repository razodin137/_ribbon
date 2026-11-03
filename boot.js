try {
  if (sessionStorage.getItem("ribbon:shell-hidden") === "1") {
    document.documentElement.classList.add("is-hidden")
  }
} catch (error) { /* storage may be unavailable */ }
