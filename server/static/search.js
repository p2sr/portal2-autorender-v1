const searchBox = document.getElementById("search");
const resultsBox = document.getElementById("video_list");

var reachedEnd = true;
var nextResult = 0;
var searchTimeout;

function createSpan(text, className="") {
	let elem = document.createElement("span");
	elem.appendChild(document.createTextNode(text));
	elem.className = className;
	return elem;
}

function createResult(data) {
	let elem = document.createElement("a");
	elem.className = "video-entry";
	if (data.obsoleted) elem.classList.add("obsoleted");
	elem.href = `/video.html?v=${data.id}`;

	elem.innerHTML = `
		<img class="thumb" src="${apiBase}/video/${data.id}/thumb"></img>
		<div class="info">
			<span>${data.user} on ${data.map}</span>
			<span>${formatTime(data.time)}</span>
			<span>${rankStr(data)}</span>
			<span class="comment">${data.comment === "" || data.comment === null ? "-" : data.comment}</span>
		</div>
		<div class="info rinfo">
			<span>${ageStr(data)}</span>
			<div class="views">
				<span class="view-count">${data.views}</span>
				<img class="view-icon" src="/eye.svg"></img>
			</div>
		</div>
	`;

	return elem;
}

function addResults(resp) {
	clearLoading();

	reachedEnd = resp.end;
	const results = resp.results;

	nextResult += results.length;

	const elem = document.createElement("div");

	results.forEach(res => resultsBox.appendChild(createResult(res)));

	// Check whether we need to add any more results
	maybeFetchMore();
}

function resetResults(resp) {
	clearLoading();

	// Clear the existing box
	// This will also remove the loading spinner
	while (resultsBox.firstChild) {
		resultsBox.removeChild(resultsBox.firstChild);
	}

	nextResult = 0;

	// If there were no results, just say that
	if (resp.results.length === 0) {
		reachedEnd = true;
		resultsBox.appendChild(document.createTextNode("No results"));
		return;
	}

	// Add the rest
	addResults(resp);
}

function maybeFetchMore() {
	const maxScroll = document.documentElement.scrollHeight - document.documentElement.clientHeight;
	const currentScroll = window.scrollY;

	if (maxScroll - currentScroll < 200) fetchMore();
}

window.addEventListener("scroll", maybeFetchMore);

var fetchingMore = false;

function fetchMore() {
	if (reachedEnd) return;
	if (fetchingMore) return;
	fetchingMore = true;
	const xhttp = new XMLHttpRequest();
	xhttp.onload = () => {
		addResults(JSON.parse(xhttp.responseText));
		fetchingMore = false;
	};
	const query = "q=" + encodeURIComponent(searchBox.value) + "&start=" + encodeURIComponent(nextResult);
	xhttp.open("GET", apiBase + "/search?" + query);
	xhttp.send();
	showLoading(false);
}

var loadingTop = false;

function showLoading(clear) {
	if (loadingTop) return;

	if (clear) {
		// Clear the existing box
		loadingTop = true;
		while (resultsBox.firstChild) {
			resultsBox.removeChild(resultsBox.firstChild);
		}
	}

	let img = document.createElement("img");
	img.id = "loading";
	img.src = "/loading.svg";

	let wrapper = document.createElement("div");
	wrapper.appendChild(img);
	wrapper.id = "loadingWrapper";

	resultsBox.appendChild(wrapper);
}

function clearLoading() {
	loadingTop = false;
	const elem = document.getElementById("loadingWrapper");
	if (elem !== null) {
		elem.remove();
	}
}

function searchUpdate() {
	const xhttp = new XMLHttpRequest();
	xhttp.onload = () => resetResults(JSON.parse(xhttp.responseText));
	const query = "q=" + encodeURIComponent(searchBox.value);
	xhttp.open("GET", apiBase + "/search?" + query);
	xhttp.send();
}

searchBox.addEventListener("beforeinput", (e) => {
	showLoading(true);
	clearTimeout(searchTimeout);
	searchTimeout = setTimeout(searchUpdate, 500);
});

searchTimeout = setTimeout(searchUpdate, 200);
