async function save(body = {}) {
	let resp;
	try {
		resp = await fetch(location.href, {
			method: 'PATCH',
			body: JSON.stringify(body),
			headers: { 'Content-Type': 'application/json' }
		});
	} catch (err) {
		showToast(err);
		return;
	}
	showToast(await resp.text());
}
function reveal_game(game) {
	document.querySelectorAll('label[data-game]').forEach(el => {
		el.style.display = el.dataset.game == game ? '' : 'none';
	});
}
function channel_ping(element, game) {
	const value = {};
	if (element.checked) value.add_game = game;
	else value.del_game = game;
	save({ channels: { [element.value]: value } });
}
window.addEventListener('load', e => {
	document.getElementById('game-select').onchange(e);
});
