const id = new URLSearchParams(window.location.search).get('v');

var videoPlayer = document.getElementById("videoPlayer");

videoPlayer.src = apiBase + "/video/" + id + "/video";

var registeredView = false;

videoPlayer.addEventListener("timeupdate", () => {
	if (registeredView) return;
	let totalPlayed = 0;
	for (let i = 0; i < videoPlayer.played.length; ++i) {
		totalPlayed += videoPlayer.played.end(i) - videoPlayer.played.start(i);
	}
	// Watching a third of the video duration is probably enough to
	// constitute a view
	if (totalPlayed > videoPlayer.duration / 3) {
		registeredView = true;
		const xhttp = new XMLHttpRequest();
		xhttp.open("POST", `${apiBase}/video/${id}/view`);
		xhttp.send();
	}
});

const xhttp = new XMLHttpRequest();
xhttp.onload = () => {
	const info = JSON.parse(xhttp.responseText);

	document.getElementById("videoTitle").innerHTML = `<a href="${boardsBase}/profile/${info.user_id}">${info.user}</a> on <a href="${boardsBase}/chamber/${info.map_id}">${info.map}</a> - ${formatTime(info.time)}`;

	document.getElementById("viewCount").innerHTML = info.views;
	document.getElementById("eye").classList.remove("hidden");
	document.getElementById("runRank").innerHTML = rankStr(info);
	document.getElementById("runDate").innerHTML = new Date(info.date).toDateString();
	document.getElementById("renderedBy").innerHTML = info.rendered_by;

	if (info.comment !== null) {
		document.getElementById("runComment").innerHTML = info.comment;
	}
};
xhttp.open("GET", apiBase + "/video/" + id + "/info");
xhttp.send();
