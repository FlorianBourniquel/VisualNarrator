#!/usr/bin/env python

import sys
import string
import os.path
import timeit
import pkg_resources

from argparse import ArgumentParser
import spacy
from jinja2 import FileSystemLoader, Environment, PackageLoader

from vn.io import Reader, Writer
from vn.miner import StoryMiner
from vn.matrix import Matrix
from vn.userstory import UserStory
from vn.utility import Printer, multiline, remove_punct, t, is_i, tab, is_comment, occurence_list, is_us
from vn.pattern import Constructor
from vn.statistics import Statistics, Counter


def initialize_nlp():
	# Initialize spaCy just once (this takes most of the time...)
	print("Initializing Natural Language Processor. . .")
	nlp = spacy.load('en')
	return nlp

def main(filename, systemname, print_us, print_ont, statistics, link, prolog, json, per_role, threshold, base, weights, spacy_nlp):

	"""General class to run the entire program
	"""

	start_nlp_time = timeit.default_timer()
	nlp = spacy_nlp
	nlp_time = timeit.default_timer() - start_nlp_time

	start_parse_time = timeit.default_timer()
	miner = StoryMiner()

	# Read the input file
	set = Reader.parse(filename)
	us_id = 1

	# Keep track of all errors	
	success = 0
	fail = 0
	list_of_fails = []
	errors = ""
	c = Counter()

	# Keeps track of all succesfully created User Stories objects
	us_instances = []  
	failed_stories = []
	success_stories = []

	# Parse every user story (remove punctuation and mine)
	for s in set:
		try:
			user_story = parse(s, us_id, systemname, nlp, miner)
			user_story = c.count(user_story)
			success = success + 1
			us_instances.append(user_story)
			success_stories.append(s)
		except ValueError as err:
			failed_stories.append([us_id, s, err.args])
			errors += "\n[User Story " + str(us_id) + " ERROR] " + str(err.args[0]) + "! (\"" + " ".join(str.split(s)) + "\")"
			fail = fail + 1
		us_id = us_id + 1

	# Print errors (if found)
	if errors:
		Printer.print_head("PARSING ERRORS")
		print(errors)

	parse_time = timeit.default_timer() - start_parse_time

	# Generate the term-by-user story matrix (m), and additional data in two other matrices
	start_matr_time = timeit.default_timer()

	matrix = Matrix(base, weights)
	matrices = matrix.generate(us_instances, ' '.join([u.sentence for u in us_instances]), nlp)
	m, count_matrix, stories_list, rme = matrices

	matr_time = timeit.default_timer() - start_matr_time

	# Print details per user story, if argument '-u'/'--print_us' is chosen
	if print_us:
		print("Details:\n")
		for us in us_instances:
			Printer.print_us_data(us)

	# Generate the ontology
	start_gen_time = timeit.default_timer()
	
	patterns = Constructor(nlp, us_instances, m)
	out = patterns.make(systemname, threshold, link)
	output_ontology, output_prolog, output_ontobj, output_prologobj, onto_per_role = out

	# Print out the ontology in the terminal, if argument '-o'/'--print_ont' is chosen
	if print_ont:
		Printer.print_head("MANCHESTER OWL")
		print(output_ontology)

	gen_time = timeit.default_timer() - start_gen_time

	# Gather statistics and print the results
	stats_time = 0
	if statistics:
		start_stats_time = timeit.default_timer()

		statsarr = Statistics.to_stats_array(us_instances)

		Printer.print_head("USER STORY STATISTICS")
		Printer.print_stats(statsarr[0], True)
		Printer.print_stats(statsarr[1], True)
		Printer.print_subhead("Term - by - User Story Matrix ( Terms w/ total weight 0 hidden )")
		hide_zero = m[(m['sum'] > 0)]
		print(hide_zero)

		stats_time = timeit.default_timer() - start_stats_time	

	# Write output files
	w = Writer()

	folder = "output/" + str(systemname)
	reports_folder = folder + "/reports"
	stats_folder = reports_folder + "/stats"

	outputfile = w.make_file(folder + "/ontology", str(systemname), "omn", output_ontology)
	files = [["Manchester Ontology", outputfile]]

	outputcsv = ""
	sent_outputcsv = ""
	matrixcsv = ""

	if statistics:
		files.append(["General statistics", w.make_file(stats_folder, str(systemname), "csv", statsarr[0])])
		files.append(["Term-by-User Story matrix", w.make_file(stats_folder, str(systemname) + "-term_by_US_matrix", "csv", m)])
		files.append(["Sentence statistics", w.make_file(stats_folder, str(systemname) + "-sentences", "csv", statsarr[1])])
	if prolog:
		files.append(["Prolog", w.make_file(folder + "/prolog", str(systemname), "pl", output_prolog)])
	if json:
		output_json_li = [str(us.toJSON()) for us in us_instances]
		output_json = "\n".join(output_json_li)
		files.append(["JSON", w.make_file(folder + "/json", str(systemname) + "-user_stories", "json", output_json)])
	if per_role:
		for o in onto_per_role:
			files.append(["Individual Ontology for '" + str(o[0]) + "'", w.make_file(folder + "/ontology", str(systemname) + "-" + str(o[0]), "omn", o[1])])

	# Print the used ontology generation settings
	Printer.print_gen_settings(matrix, base, threshold)

	# Print details of the generation
	Printer.print_details(fail, success, nlp_time, parse_time, matr_time, gen_time, stats_time)

	report_dict = {
		"stories": us_instances,
		"failed_stories": failed_stories,
		"systemname": systemname,
		"us_success": success,
		"us_fail": fail,
		"times": [["Initializing Natural Language Processor (<em>spaCy</em> v" + pkg_resources.get_distribution("spacy").version + ")" , nlp_time], ["Mining User Stories", parse_time], ["Creating Factor Matrix", matr_time], ["Generating Manchester Ontology", gen_time], ["Gathering statistics", stats_time]],
		"dir": os.path.dirname(os.path.realpath(__file__)),
		"inputfile": filename,
		"inputfile_lines": len(set),
		"outputfiles": files,
		"threshold": threshold,
		"base": base,
		"matrix": matrix,
		"weights": m['sum'].copy().reset_index().sort_values(['sum'], ascending=False).values.tolist(),
		"counts": count_matrix.reset_index().values.tolist(),
		"classes": output_ontobj.classes,
		"relationships": output_prologobj.relationships,
		"types": list(count_matrix.columns.values),
		"ontology": multiline(output_ontology)
	}

	# Finally, generate a report
	report = w.make_file(reports_folder, str(systemname) + "_REPORT", "html", generate_report(report_dict))
	files.append(["Report", report])

	# Print the location and name of all output files
	for file in files:
		if str(file[1]) != "":
			print(str(file[0]) + " file succesfully created at: \"" + str(file[1]) + "\"")
	
	# Return objects so that they can be used as input for other tools
	return {'us_instances': us_instances, 'output_ontobj': output_ontobj, 'output_prologobj': output_prologobj, 'matrix': m}


def parse(text, id, systemname, nlp, miner):
	"""Create a new user story object and mines it to map all data in the user story text to a predefined model
	
	:param text: The user story text
	:param id: The user story ID, which can later be used to identify the user story
	:param systemname: Name of the system this user story belongs to
	:param nlp: Natural Language Processor (spaCy)
	:param miner: instance of class Miner
	:returns: A new user story object
	"""
	no_punct = remove_punct(text)
	no_double_space = ' '.join(no_punct.split())
	doc = nlp(no_double_space)
	user_story = UserStory(id, text, no_double_space)
	user_story.system.main = nlp(systemname)[0]
	user_story.data = doc
	#Printer.print_dependencies(user_story)
	#Printer.print_noun_phrases(user_story)
	miner.structure(user_story)
	user_story.old_data = user_story.data
	user_story.data = nlp(user_story.sentence)
	miner.mine(user_story, nlp)
	return user_story
	
def generate_report(report_dict):
	"""Generates a report using Jinja2
	
	:param report_dict: Dictionary containing all variables used in the report
	:returns: HTML page
	"""
	CURR_DIR = os.path.dirname(os.path.abspath(__file__))

	loader = FileSystemLoader( searchpath=str(CURR_DIR) + "/templates/" )
	env = Environment( loader=loader, trim_blocks=True, lstrip_blocks=True )
	env.globals['text'] = t
	env.globals['is_i'] = is_i
	env.globals['apply_tab'] = tab
	env.globals['is_comment'] = is_comment
	env.globals['occurence_list'] = occurence_list
	env.tests['is_us'] = is_us
	template = env.get_template("report.html")

	return template.render(report_dict)


def call(filename, spacy_nlp):
	args2 = program("--return-args")
	weights = [args2.weight_func_role, args2.weight_main_obj, args2.weight_ff_means, args2.weight_ff_ends,
			   args2.weight_compound]
	filename = open(filename)
	return main(filename, args2.system_name, args2.print_us, args2.print_ont, args2.statistics, args2.link, args2.prolog,
				args2.json, args2.per_role, args2.threshold, args2.base_weight, weights, spacy_nlp)


def program(*args):
	p = ArgumentParser(
		usage='''run.py <INPUT FILE> [<args>]

///////////////////////////////////////////
//              Visual Narrator          //
///////////////////////////////////////////

This program has multiple functionalities:
	(1) Mine user story information
	(2) Generate an ontology from a user story set
	(3) Generate Prolog from a user story set (including links to 'role', 'means' and 'ends')
	(4) Get statistics for a user story set
''',
		epilog='''{*} Utrecht University.
			M.J. Robeer, 2015-2017''')

	if "--return-args" not in args:
		p.add_argument("filename",
					 help="input file with user stories", metavar="INPUT FILE",
					 type=lambda x: is_valid_file(p, x))
	p.add_argument('--version', action='version', version='Visual Narrator v0.9 BETA by M.J. Robeer')

	g_p = p.add_argument_group("general arguments (optional)")
	g_p.add_argument("-n", "--name", dest="system_name", help="your system name, as used in ontology and output file(s) generation", required=False)
	g_p.add_argument("-u", "--print_us", dest="print_us", help="print data per user story in the console", action="store_true", default=False)
	g_p.add_argument("-o", "--print_ont", dest="print_ont", help="print ontology in the console", action="store_true", default=False)
	g_p.add_argument("-l", "--link", dest="link", help="link ontology classes to user story they originate from", action="store_true", default=False)
	g_p.add_argument("--prolog", dest="prolog", help="generate prolog output (.pl)", action="store_true", default=False)
	g_p.add_argument("--return-args", dest="return_args", help="return arguments instead of call VN", action="store_true", default=False)
	g_p.add_argument("--json", dest="json", help="export user stories as json (.json)", action="store_true", default=False)
	g_p.add_argument("--split", dest="split", help="Process the stories one by one", action="store_true", default=False)
	s_p = p.add_argument_group("statistics arguments (optional)")
	s_p.add_argument("-s", "--statistics", dest="statistics", help="show user story set statistics and output these to a .csv file", action="store_true", default=False)

	w_p = p.add_argument_group("conceptual model generation tuning (optional)")
	w_p.add_argument("-p", "--per_role", dest="per_role", help="create an additional conceptual model per role", action="store_true", default=False)
	w_p.add_argument("-t", dest="threshold", help="set threshold for conceptual model generation (INT, default = 1.0)", type=float, default=1.0)
	w_p.add_argument("-b", dest="base_weight", help="set the base weight (INT, default = 1)", type=int, default=1)	
	w_p.add_argument("-wfr", dest="weight_func_role", help="weight of functional role (FLOAT, default = 1.0)", type=float, default=1)
	w_p.add_argument("-wdo", dest="weight_main_obj", help="weight of main object (FLOAT, default = 1.0)", type=float, default=1)
	w_p.add_argument("-wffm", dest="weight_ff_means", help="weight of noun in free form means (FLOAT, default = 0.7)", type=float, default=0.7)
	w_p.add_argument("-wffe", dest="weight_ff_ends", help="weight of noun in free form ends (FLOAT, default = 0.5)", type=float, default=0.5)		
	w_p.add_argument("-wcompound", dest="weight_compound", help="weight of nouns in compound compared to head (FLOAT, default = 0.66)", type=float, default=0.66)		
	
	if (len(args) < 1):
		args = p.parse_args()
	else:
		args = p.parse_args(args)

	weights = [args.weight_func_role, args.weight_main_obj, args.weight_ff_means, args.weight_ff_ends, args.weight_compound]

	if not args.system_name or args.system_name == '':
		args.system_name = "System"
	if not args.return_args:
		spacy_nlp = initialize_nlp()
		if args.split:
			stories = Reader.parse(args.filename)
			for s in stories:
				file = open('./tmp.txt', 'w+')
				file.write(s)
				file.close()
				main(open('./tmp.txt', 'r'), args.system_name, args.print_us, args.print_ont, args.statistics, args.link, args.prolog, args.json, args.per_role, args.threshold, args.base_weight, weights, spacy_nlp)
			return
		else:
			return main(args.filename, args.system_name, args.print_us, args.print_ont, args.statistics, args.link, args.prolog, args.json, args.per_role, args.threshold, args.base_weight, weights, spacy_nlp)
	else:
		return args

def is_valid_file(parser, arg):
	if not os.path.exists(arg):
		parser.error("Could not find file " + str(arg) + "!")
	else:
		return open(arg, 'r')


if __name__ == "__main__":
	program()
