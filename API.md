GET /api/search?q=thing[&start=0]
Search for the given query, possibly starting at the given result offset.
	{
		"results": [
			{
				"id": 123456,
				"user": "mlugg",
				"map": "Future Starter",
				"time": 1234,    // 12.34s
				"cur_rank": 4,
				"orig_rank": 3,
				"date": "2021-01-01T00:00:00Z",
				"views": 1000
			},
			{
				"id": 567890,
				"user": "finowo",
				"map": "Portal Gun",
				"time": 9430,
				"cur_rank": null,   // no longer t200
				"orig_rank": 198,
				"date": "2021-01-02T09:30:00Z",
				"views": 4
			}
		],
		"end": false,    // true if we've reached the end of the results
	}

GET /api/video/info/123456
Get info about the given video.
	{
		"id": 123456,
		"user": "mlugg",
		"map": "Future Starter",
		"time": 1234,
		"cur_rank": 4,
		"orig_rank": 3,
		"date": "2021-01-01T00:00:00Z",
		"views": 1000
	}

GET /api/video/thumb/123456
GET /api/video/video/123456

POST /api/video/view/123456
Add a view to a video.
	{}

----------------------------------------------------------------------------------------

GET /api/upload/pending
List the videos pending upload.
	{
		"changelog_ids": [
			123456,
			234567,
			345678
		]
	}
	X-Auth-Token: abcdef

PUT /api/upload/video/123456
[with file content lol]
	{}
	X-Auth-Token: abcdef

POST /api/upload/error
	{
		"changelog_ids": [
			123456,
			345678
		]
	}
	{}
	X-Auth-Token: abcdef
