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

const getCookie = (name) => {
	let decoded = decodeURIComponent(document.cookie);
	let ca = decoded.split(';');
	for (let i = 0; i < ca.length; ++i) {
		let c = ca[i];
		while (c.charAt(0) == ' ') c = c.substring(1);
		if (c.indexOf(`${name}=`) == 0) {
			return c.substring(name.length + 1);
		}
	}
	return "";
};

const setCookie = (name, val) => {
	const d = new Date();
	d.setTime(d.getTime() + (90*24*60*60*1000)); // 90 days
	document.cookie = `${name}=${val};expires=${d.toUTCString()};path=/`;
};

{
	let vol = getCookie("video-volume");
	if (vol != "") {
		videoPlayer.volume = vol;
	} else {
		setCookie("video-volume", videoPlayer.volume);
	}

	videoPlayer.addEventListener("volumechange", (e) => {
		setCookie("video-volume", videoPlayer.volume);
	});
}

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
