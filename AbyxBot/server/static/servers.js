function toggle(element, ext, set) {
	let img = element.children[0].children[0];
	if (set) img.src = img.src.replace('.png', ext);
	else img.src = img.src.replace(ext, '.png');
}
