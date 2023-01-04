function showToast(content) {
	let element = document.createElement('div');
	element.classList = ['toast-notif'];
	element.innerText = content;
	document.body.appendChild(element);
	setTimeout(() => {element.classList.add('show');}, 100);
	setTimeout(() => {
		element.classList.remove('show');
	}, 3100);
	setTimeout(() => {
		element.remove();
	}, 3600); // 3.1s + 0.5s transition
}
