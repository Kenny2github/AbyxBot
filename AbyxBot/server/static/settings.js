function promptSave(event) {
	event.preventDefault();
	// browsers don't respect prompts
	// and the default one is fine anyway
	event.returnValue = null;
}
function enableSave() {
	const element = document.querySelector('[type=submit][disabled]');
	if (element) {
		element.disabled = false;
		// only add event listener now
		window.addEventListener('beforeunload', promptSave);
	}
}
