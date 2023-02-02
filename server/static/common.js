const apiBase = "https://autorender.portal2.sr/api/v1";
const boardsBase = "https://board.portal2.sr";

function formatTime(total) {
	const cs = total % 100;
	total = Math.floor(total / 100);

	const secs = total % 60;
	total = Math.floor(total / 60);

	const mins = total;

	const cs_str = cs < 10 ? "0" + cs : cs;
	const secs_str = mins > 0 && secs < 10 ? "0" + secs : secs;

	let str = secs_str + "." + cs_str;
	if (mins > 0) str = mins + ":" + str

	return str;
}

function ordinal(n) {
	if (n > 10 && n < 20) return n + "th";

	if (n % 10 == 1) return n + "st";
	if (n % 10 == 2) return n + "nd";
	if (n % 10 == 3) return n + "rd";

	return n + "th";
}

function rankStr(data) {
	let str = `${ordinal(data.orig_rank)} place`;
	if (data.cur_rank === null) {
		str += " (obsolete)";
	} else if (data.cur_rank !== data.orig_rank) {
		str += ` (now ${ordinal(data.cur_rank)})`;
	}
	return str;
}

function ageStr(data) {
	const diff = Date.now() - new Date(data.date).getTime();

	const day = 24 * 60 * 60 * 1000;
	const mon = 30 * day;
	const year = 365.25 * day;

	if (diff > year) {
		return Math.floor(diff / year) + "y";
	}

	if (diff > mon) {
		return Math.floor(diff / mon) + "m";
	}

	if (diff > day) {
		return Math.floor(diff / day) + "d";
	}

	return "today";
}
