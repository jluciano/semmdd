import numpy as np
import math
import optparse
import datetime
import time
from SPARQLWrapper import SPARQLWrapper, JSON

class data_preproc:
	""" Class that sets up the connection to the SPARQL Endpoint, gets the data you want, preprocesses (splines & normalizes) the data, and
	has an interface for accessing the data """
	
	def __init__(self):
		""" Really nothing to initalize here """
		self.sparql_interface = SPARQLWrapper('http://localhost:8080/sparql')
		self.sparql_interface.setReturnFormat(JSON)
		self.sparql_interface.setQuery('select distinct ?Concept where {[] a ?Concept} LIMIT 1')
		self.data_loaded = False
		self.data_preprocessed = False
		# Test to make sure connection works
		try:
			self.sparql_interface.query()
		except URLError:
			print "Could not connect to SPARQL Endpoint. Make sure the port forwarding is running and you are on the RPI network"
			raise IOError


	def load(self, study='UPittSSRI', chosen_quests=['1','2','3','4','5','6','7','8','10','13'], norm=True):
		""" Loads data from the specified study, currently the only option is 'UPittSSRI'
				Returns a list of patient ids."""
		try:
			query = self.make_query(study, chosen_quests)
			self.sparql_interface.setQuery(query)
			print "Retrieving data"
			tic = time.time()
			raw_data = self.sparql_interface.query().convert()
			toc = time.time() - tic
			print "Took %f seconds" % toc
			print "Making data usable"
			tic = time.time()
			try:
				self.data = self.make_usable(raw_data, chosen_quests, norm)
			except ValueError:
				raise ValueError
			toc = time.time() - tic
			print "Took %f seconds" % toc
			self.data_loaded = True
			return self.data.keys()
		except IOError as detail:
			print "Could not retrieve data:", detail
			self.data_loaded = False
			return None

	def make_query(self, study, chosen_quests):
		""" Internal to use the name of a study to make a final query. For some data we need to make multiple queries """
		if study == 'UPittSSRI':
			# Handle specific case of UPittSSRI data
			# First, make and send query to get list of patients that terminated the study correctly
			# Thanks Brendan Ashby for the queries
			patientTerminationsQuery = """
			prefix dcterms: <http://purl.org/dc/terms/>
			prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
			prefix dataset: <http://purl.org/twc/semmdd/source/pican-wpic-pitt-edu/dataset/ppli-ssri/version/2012-09-08>
			prefix e1: <http://purl.org/twc/semmdd/source/pican-wpic-pitt-edu/dataset/ppli-ssri/vocab/enhancement/1/>
			prefix foaf: <http://xmlns.com/foaf/0.1/>
			select ?patient
			where 
			{
			?termentry dcterms:isReferencedBy dataset: .
			?termentry e1:term \"0\" .
			?termentry 
			foaf:isPrimaryTopicOf ?patient
			}"""
		 
			self.sparql_interface.setQuery(patientTerminationsQuery)

			prop_term_raw = self.sparql_interface.query().convert()
			prop_term = [i['patient']['value'].split('/')[-1] for i in prop_term_raw['results']['bindings']]
			# Second, use this list to get their responses over time
			# Use this list of questions to filter out the ones we don't want. This list is chosen manually and will be for the forseeable future
			prop_term_string = ','.join(['completedpatientID:' + i for i in prop_term])
			chosen_quests_string = ','.join(['question:' + i for i in chosen_quests])

			main_query = """
			prefix completedpatientID: <http://purl.org/twc/semmdd/source/pican-wpic-pitt-edu/dataset/ppli-ssri/ppli-hams.xls/typed/patient/>
			prefix datasetvocab: <http://purl.org/twc/semmdd/source/pican-wpic-pitt-edu/dataset/ppli-ssri/vocab/>
			prefix datasetmeasurement: <http://purl.org/twc/semmdd/source/pican-wpic-pitt-edu/dataset/ppli-ssri/ppli-hams.xls/version/2012-09-08/>
			prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nprefix openvocab: <http://open.vocab.org/terms/>
			prefix measurementanswer: <http://purl.org/twc/semmdd/source/pican-wpic-pitt-edu/dataset/ppli-ssri/vocab/enhancement/1/>
			prefix foaf: <http://xmlns.com/foaf/0.1/>
			prefix dcterms: <http://purl.org/dc/terms/>
			prefix question: <http://purl.org/twc/semmdd/source/pican-wpic-pitt-edu/dataset/ppli-ssri/Q>
			select distinct ?patient ?cdate ?column ?question ?answer 
			where
			{
			?Measurement rdf:type	datasetvocab:Measurement .
			?Measurement openvocab:csvCol ?column .
			?Measurement measurementanswer:for_question ?question .
			FILTER ( ?question IN (""" + chosen_quests_string + """)) .
			?Measurement measurementanswer:hasAnswer ?answer .
			?Measurement foaf:isPrimaryTopicOf ?patient .
			FILTER ( ?patient IN (""" + prop_term_string + """)) .
			?Measurement dcterms:created ?cdate
			}"""

		return main_query

	def make_usable(self, raw_data, chosen_quests, norm=True):
		""" Internal function that turns the SPARQL output into something the model can use """
		# We need to interpret the data into a usable format. We'll start by making a dictionary keyed on each patient, with
		# the items being a dictionary of date:list of responses. 
		question_slots = {'Q'+i:ind for ind, i in enumerate(chosen_quests)}
		shaped_data = dict()

		for i in raw_data['results']['bindings']:
			patient_id = i['patient']['value'].split('/')[-1]
			response_date = datetime.date(*[int(j) for j in i['cdate']['value'].split('-')])
			question = i['question']['value'].split('/')[-1]
			question_slot = question_slots[question]
			answer = int(i['answer']['value'].split('/')[-1])
			normed_answer = answer / float(max_ham[question])
			
			# First setup a dictionary for the patient if one does not already exist
			if not patient_id in shaped_data:
				shaped_data[patient_id] = dict()
																								
			# Then setup the list for the date in that patient's data, if it hasn't already been encountered
			if not response_date in shaped_data[patient_id]:
				shaped_data[patient_id][response_date] = [None for j in question_slots.keys()]

			# Then put the answer in the appropriate slot
			# But first, raise an error if it's already been filled... clearly something got screwed up -- I have already checked this and the data is fine
			if shaped_data[patient_id][response_date][question_slot] != None:
				print "Conflicting data. Abort."
				print "Patient ID %s's response to question %s on date %s has already been filled with value %d" (patient_id, question, response_date.ctime(), answer)
				raise ValueError																																								    
			if norm:
				shaped_data[patient_id][response_date][question_slot] = normed_answer
			else:	
				shaped_data[patient_id][response_date][question_slot] = answer

		# Now that we've shaped the data, we need to order it by date for the model. Simple enough
		ordered_data = dict()
		for patient in shaped_data:
			ordered_data[patient] = dict()
			ordered_data[patient]['dates'] = []
			ordered_data[patient]['data'] = []
			for date in sorted(shaped_data[patient].iterkeys()):
				ordered_data[patient]['data'].append(shaped_data[patient][date])
				ordered_data[patient]['dates'].append(date)

		# And we're done here

		self.ordered_data = ordered_data
		return ordered_data

	def prefilter(self, keep_days=124, min_days=31, min_data=4):
		""" Normalizes data, sets up data to use the spline """
		# Requires load to be run first, so we'll check that.
		removed = 0
		filtered_data = dict()
		if not self.data_loaded:
			print "You need to load the data before you can preprocess it"
			raise ValueError

		# Pass through the data
		for patient in self.ordered_data:
			# First we're going to cut out any data after the number of days specified by keep_days
			length = math.fabs((self.ordered_data[patient]['dates'][-1] - self.ordered_data[patient]['dates'][0]).days)
			if length < min_days:
				# Also skip if there's less than min_days
				removed += 1
				continue

			initial_date = self.ordered_data[patient]['dates'][0]
			final_ind = 0
			for date_ind, date in enumerate(self.ordered_data[patient]['dates'][1:]):
				num_days = (date - initial_date).days
				final_ind += 1
				if num_days >= keep_days:
					break
			
			# Then we're going to cut out any patient with less than 4 datapoints. This is for cubic splining's sake

			if final_ind < min_data:
				removed += 1
				continue

			# now that all of this filtering is done, let's build our filtered_data entry
			filtered_data[patient] = dict()
			filtered_data[patient]['data'] = self.ordered_data[patient]['data'][:final_ind+1]
			filtered_data[patient]['dates'] = self.ordered_data[patient]['dates'][:final_ind+1]


	
	def spline(self, k=1, s=1, min_data=3):
		""" Interpolates uneven observation data into daily data using scipy.interpolate.UnivariateSpline with parameters k and s given"""


		pass
	

	def retrieve(self, patient_id):
		""" Returns the data for the specified patient id """
		return self.data[patient_id]


class luciano_model:
	
	def __init__(self, params):
		self.params = params

	def load_data(self, data_preproc):
		""" Give the model a data_preproc object to work with """
		pass

	def init_params(self):
		pass




if __name__ == '__main__':
	# Just load the UPittSSRI data and print off the first patient
	data_obj = data_preproc()
	data_obj.load('UPittSSRI')
	print "Patient 1's data:"
	print data_obj.retrieve('1')
