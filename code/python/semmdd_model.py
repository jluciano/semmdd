import numpy as np
import math
import optparse
import datetime
import time
import cPickle as pickle
from urllib2 import URLError
from SPARQLWrapper import SPARQLWrapper, JSON
from scipy.interpolate import UnivariateSpline

class data_preproc:
	""" Class that sets up the connection to the SPARQL Endpoint, gets the data you want, preprocesses (splines & normalizes) the data, and
	has an interface for accessing the data """
	
	def __init__(self):
		""" Really nothing to initalize here """
		self.sparql_interface = SPARQLWrapper('http://localhost:8080/sparql')
		self.sparql_interface.setReturnFormat(JSON)
		self.data_loaded = False
		self.data_preprocessed = False
		self.data_splined = False

		self.ordered_data = None
		self.filtered_data = None
		self.splined_data = None

		self.removed = None
		self.keep_days = None
		self.min_days = None
		self.min_data = None
		self.spline_err = None
		self.max_ham = {
							'Q1':4,
							'Q2':4,
							'Q3':4,
							'Q4':2,
							'Q5':2,
							'Q6':2,
							'Q7':4,
							'Q8':4,
							'Q9':4,
							'Q10':4,
							'Q11':4,
							'Q12':2,
							'Q13':2,
							'Q14':2,
							'Q15':4,
							'Q16':2,
							'Q17':2, # Should add a/b/c but these are optional and not handled by model yet, also mostly missing
							'Q18':2,
							'Q19':2,
							'Q20':2,
							'Q21':2,
							'Q22':2, # similar to 17 wrt optional
							'Q23':4,
							'Q24':4,
							'Q25':2,
							'Q26':4,
							'Q27':4,
							'Q28':4
		}


	def load(self, loadfile=None, savefile=None, study='UPittSSRI', chosen_quests=[str(i) for i in range(1,29)], norm=True):
		""" Loads data from the specified study, currently the only option is 'UPittSSRI'
				Returns a list of patient ids."""
		if loadfile != None:
			# Ability to load previously saved datasets to avoid having to pull it from the database
			try:
				loadfilefo = open(loadfile, 'r')
				self.ordered_data = pickle.load(loadfilefo)
				loadfilefo.close()
				self.data = self.ordered_data
				self.num_items = len(self.data[self.data.keys()[0]]['data'][0])
				self.data_loaded = True
				return self.ordered_data.keys()
			except IOError:
				raise IOError	
		try:
			self.num_items = len(chosen_quests)
			query = self.make_query(study, chosen_quests)
			self.sparql_interface.setQuery(query)
			print "Retrieving data"
			tic = time.time()
			try:
				raw_data = self.sparql_interface.query().convert()
			except URLError:
				print "Could not connect to SPARQL Endpoint. Make sure the port forwarding is running and you are on the RPI network"
				raise IOError
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
			if savefile != None:
				try:
					savefilefo = open(savefile, 'w')
					pickle.dump(self.data, savefilefo)
					savefilefo.close()
				except IOError:
					raise IOError
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
			prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
			prefix openvocab: <http://open.vocab.org/terms/>
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
		rows_added = 0
		redundant_rows = 0
		conflicting_rows = 0
		for i in raw_data['results']['bindings']:
			patient_id = i['patient']['value'].split('/')[-1]
			response_date = datetime.date(*[int(j) for j in i['cdate']['value'].split('-')])
			question = i['question']['value'].split('/')[-1]
			question_slot = question_slots[question]
			answer = int(i['answer']['value'].split('/')[-1])
			if norm:
				answer /= float(self.max_ham[question])
			
			# First setup a dictionary for the patient if one does not already exist
			if not patient_id in shaped_data:
				shaped_data[patient_id] = dict()
																								
			# Then setup the list for the date in that patient's data, if it hasn't already been encountered
			if not response_date in shaped_data[patient_id]:
				shaped_data[patient_id][response_date] = [None for j in question_slots.keys()]

			# Then put the answer in the appropriate slot
			# But first, raise an error if it's already been filled... clearly something got screwed up -- I have already checked this and the data is fine
			if shaped_data[patient_id][response_date][question_slot] != None:
				current = shaped_data[patient_id][response_date][question_slot]				
				conflict_string =  "Patient ID %s's response to question %s on date %s has already been filled with value %0.2f" % (patient_id, question, response_date.ctime(), current)
				if current == answer:
					redundant_rows += 1
					conflict_string += " -- Redundant"
				else:
					conflicting_rows += 1
					conflict_string += " -- Conflicting, trying to use %0.2f" % answer 
				print conflict_string
				continue																																							    	
			shaped_data[patient_id][response_date][question_slot] = answer
			rows_added += 1
		print "Digested %d rows, of which %d were redundant and %d were conflicting" % (rows_added, redundant_rows, conflicting_rows)

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
		self.removed = 0
		self.keep_days = keep_days
		self.min_days = min_days
		self.min_data = min_data
		if not self.data_loaded:
			print "You need to load the data before you can preprocess it"
			raise ValueError

		filtered_data = dict()
		# Pass through the data
		for patient in self.ordered_data:
			# First we're going to cut out any data after the number of days specified by keep_days
			length = math.fabs((self.ordered_data[patient]['dates'][-1] - self.ordered_data[patient]['dates'][0]).days)
			if length < min_days:
				# Also skip if there's less than min_days
				self.removed += 1
				continue

			initial_date = self.ordered_data[patient]['dates'][0]
			final_ind = 1
			for date_ind, date in enumerate(self.ordered_data[patient]['dates'][1:]):
				num_days = (date - initial_date).days
				if num_days >= keep_days:
					break	
				final_ind += 1
			# Then we're going to cut out any patient with less than 4 datapoints. This is for cubic splining's sake

			if final_ind < min_data:
				self.removed += 1
				continue

			# now that all of this filtering is done, let's build our filtered_data entry
			filtered_data[patient] = dict()
			filtered_data[patient]['data'] = self.ordered_data[patient]['data'][:final_ind]
			filtered_data[patient]['dates'] = self.ordered_data[patient]['dates'][:final_ind]

		self.filtered_data = filtered_data
		self.data = filtered_data
		return filtered_data
	
	def spline(self, k=3, s=0.5):
		""" Interpolates uneven observation data into daily data using scipy.interpolate.UnivariateSpline with parameters k and s given"""
		# requires filtered_data to exist, check by making sure it isn't empty
		if len(self.filtered_data) == 0:
			raise ValueError

		# first we need to redo the dates as days from start
		for patient in self.filtered_data:
			self.filtered_data[patient]['days'] = []
			for date in self.filtered_data[patient]['dates']:
				since_beginning = (date - self.filtered_data[patient]['dates'][0]).days
				self.filtered_data[patient]['days'].append(since_beginning)

		# now we spline
		error = 0
		splined_data = dict()
		for patient in self.filtered_data:
			day_indices = np.array(self.filtered_data[patient]['days'])
			splined_data[patient] = []
			for question in range(self.num_items):
				item_data = np.array([i[question] for i in self.filtered_data[patient]['data']])
				if len(item_data) == 0:
					print "Uh, no responses for question %d patient %s" % (question+1, patient)
					raise ValueError
				# Now we need to take out the data with None values... not certain how to handle it if the patient ends up not having enough data
				# because of this filtering, but for UPittSSRI data (primary focus as of 7/29/13) we don't need to worry about it
				good_indices = np.array([ind for ind, resp in enumerate(item_data) if resp != None])
				filtered_days = day_indices[good_indices]
				filtered_data = item_data[good_indices]
				full_space = np.linspace(0,self.keep_days,num=self.keep_days)
				spl = UnivariateSpline(filtered_days, filtered_data, k=k, s=s)
				self.residual = spl.get_residual()
				self.knots = spl.get_knots()
				splined = spl(full_space)
				splined_data[patient].append(splined)
				# Measure error
				ms = math.sqrt(sum((splined[filtered_days] - filtered_data)**2)/len(filtered_data))
				error += ms
			splined_data[patient] = np.array(splined_data[patient]).T
		error /= (self.num_items)*(len(splined_data))
		self.spline_err = error

		self.splined_data = splined_data
		self.data_splined = True
		self.data = splined_data
		return splined_data

	def retrieve(self, patient_id):
		""" Returns the data for the specified patient id """
		return self.data[patient_id]

	def get_keys(self):
		""" Gets a list of the patients available in the current data. Note that this may change after each step as patients might be removed """
		return self.data.keys()

	


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
	data_obj.load(study='UPittSSRI', savefile='UPittSSRI.dat')
	data_obj.prefilter()
	data_obj.spline()
	print "Patient 1's data:"
	print data_obj.retrieve('1')
