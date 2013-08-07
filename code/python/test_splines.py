import sys
import numpy as np
import os

sys.path.insert(0, '../../../') # Laziness hack to import semmdd_model without copying it into the spearmint/test_splines directory
from semmdd_model import data_preproc
sys.path.pop(0)


def main(job_id, params):
	#study = params['study'][0]
	study = 'UPittSSRI'
	k = int(params['spline_degree'][0])
	s = params['smoothing'][0]
	# script to test the spline error
	preproc = data_preproc()

	chosen_quests = [str(i) for i in range(1,29)]

	studyfile = study + '.dat'

	if not os.path.exists(studyfile): 
		# well now we need to create the file
		print "Could not find %s, attempting to download from SPARQL database" % studyfile
		try:
			preproc.load(study=study, savefile=studyfile, chosen_quests=chosen_quests)
		except IOError:
			print "Make sure you're connected"
			sys.exit(2)
	else:
		preproc.load(loadfile=studyfile)

	preproc.prefilter()
	preproc.spline(k=k,s=s)
	error = preproc.spline_err
	if np.isnan(error):
		# This will happen if the smoothing is too low. I will set it to an unacceptable value like 1
		error = 1.0

	print "Error with k = %d and s = %f is: %f" % (k, s, error)
	return error


if __name__ == "__main__":
	params = {
		"spline_degree": "1",
		"smoothing": 1,
		"study": "UPittSSRI"
		}
	job_id = 0
	main(job_id, params)
