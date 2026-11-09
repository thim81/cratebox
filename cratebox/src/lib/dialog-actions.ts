export function confirmOnEnter(
  event: { key: string; preventDefault: () => void; stopPropagation: () => void },
  confirm: () => void,
  disabled = false,
) {
  if (event.key !== "Enter" || disabled) return;
  event.preventDefault();
  event.stopPropagation();
  confirm();
}
