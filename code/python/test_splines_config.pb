language: PYTHON
name: "test_splines"

variable {
	name: "spline_degree"
	type: ENUM
	size: 1
	options: "1"
	options: "2"
	options: "3"
}

variable {
	name: "smoothing"
	type: FLOAT
	size: 1
	min: 0.5
	max: 10
}

#variable {
#	name: "study"
#	type: ENUM
#	size: 1
#	options: "UPittSSRI"
#}
