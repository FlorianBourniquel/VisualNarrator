from app.helper import Helper
from lang.en.indicators import *

class StoryMiner:
	def mine(self, story):
		story = self.get_indicators(story)
		if not story.role.indicator:
			raise ValueError('Could not find a role indicator', 0)
		if not story.means.indicator:
			raise ValueError('Could not find a means indicator', 1)
		story = self.get_functional_role(story)
		if not story.role.functional_role:
			raise ValueError('Could not find a functional role', 2)
		story = self.get_main_verb(story)
		if not story.means.main_verb.main:
			raise ValueError('Could not find a main verb', 3)
		story = self.get_direct_object(story)
		if not story.means.direct_object.main:
			raise ValueError('Could not find a direct object', 4)	
		story = self.get_free_form(story)

	def get_indicators(self, story):
		returnlist = []
		rm = MinerHelper.reasonable_max(story.data)
		indicators = [['Role', rm[0]], ['Means', rm[1]], ['Ends', rm[2]]]
		for indicator in indicators:
			found_ind = self.get_one_indicator(story.data, indicator[0], indicator[1])
			returnlist.append(found_ind)
			story.indicators.extend(found_ind)
		story.role.indicator = returnlist[0]
		story.means.indicator = returnlist[1]
		story.ends.indicator = returnlist[2]
		return story

	def get_one_indicator(self, story_data, indicator_type, reasonable_max):
		pattern = [x.split(' ') for x in eval(indicator_type.upper() + '_INDICATORS')]
		present_pattern = []
		for p in pattern:
			if Helper.is_sublist([MinerHelper.lower(pl) for pl in p], [MinerHelper.lower(sd) for sd in Helper.get_tokens(story_data[0:reasonable_max])]):
				present_pattern.append(p)		
		found = False
		found_pattern = []
		for p in present_pattern:
			for s in story_data:
				if MinerHelper.lower(p[0]) == MinerHelper.lower(s.text):
					found_pattern.append(story_data[s.i:s.i++len(p)]) 
					found = True					
		if found:
			return max(found_pattern, key=len)
		return []

	def get_functional_role(self, story):
		role = story.role.indicator[0].right_edge
		story.role.functional_role.main = role
		story.role.functional_role.adjectives = MinerHelper.get_span(story, role.children)
		return story

	def get_main_verb(self, story):
		last_idx = story.means.indicator[-1].i
		main_verb = story.data[last_idx].nbor(1)

		story.means.main_verb.main = main_verb
		
		pv = MinerHelper.get_phrasal_verb(story, main_verb)
		story.means.main_verb.phrase = MinerHelper.get_span(story, pv[0])
		story.means.main_verb.type = pv[1]

		return story

	def get_direct_object(self, story):
		if not story.means.main_verb.phrase:
			pointer = story.means.main_verb.main
		else:
			phrase = story.means.main_verb.phrase
			pointer = phrase[-1]
	
		np = MinerHelper.get_noun_phrase(story, pointer)
		story.means.direct_object.main = np[0]
		story.means.direct_object.phrase = np[1]

		return story

	def get_free_form(self, story):
		list = []

		func_role = []
		func_role.append(story.role.functional_role.main)
		func_role.extend(story.role.functional_role.adjectives)

		main_verb = []
		main_verb.append(story.means.main_verb.main)
		main_verb.extend(story.means.main_verb.phrase)

		direct_obj = []
		direct_obj.append(story.means.direct_object.main)
		direct_obj.extend(story.means.direct_object.phrase)		

		not_free_form = story.indicators + func_role + main_verb + direct_obj

		for token in story.data:
			if token not in not_free_form:
				list.append(token)
		
		story.free_form = MinerHelper.get_span(story, list)

		means_free_form = []
		ends_free_form = []
		for token in story.free_form:
			if story.ends.indicator and token.i > story.ends.indicator[-1].i:
				ends_free_form.append(token)
			else:
				means_free_form.append(token)
		
		story.means.free_form = MinerHelper.get_span(story, means_free_form)
		story.ends.free_form = MinerHelper.get_span(story, ends_free_form)

		return story


class MinerHelper:
	# Fixes that a real lower string is used, instead of a reference
	def lower(str):
		return str.lower()

	def reasonable_max(doc):
		rm = []
		l = len(doc)
		if l > 1:
			rm.append(2)	# Role
		else:
			rm.append(l)
		if l - 1 > 12:		# Means
			rm.append(12)
		else:
			rm.append(l)
		rm.append(l)		# Ends
		return rm 

	# Fixes that spaCy dependencies are not spans, but temporary objects that get deleted when loaded into memory
	def get_span(story, li):
		ret = []
		idxlist = Helper.get_idx(li)
		for i in idxlist:
			ret.append(story.data[i])
		return ret

	# Obtain noun phrases (including form 'x of y')
	def get_noun_phrase(story, pointer):
		phrase = []
		main = []

		for chunk in story.data.noun_chunks:
			if pointer == chunk.root.head:
				phrase = MinerHelper.get_span(story, chunk)

		if phrase:
			main = phrase[-1]
			if phrase[-1].i < story.data[-1].i:
				potential_of = story.data[phrase[-1].i + 1]
				if MinerHelper.lower(potential_of.text) == 'of':
					for chunk in story.data.noun_chunks:
						if chunk.root.head == potential_of:	
							phrase.append(potential_of)	
							phrase.extend(MinerHelper.get_span(story, chunk))
		elif pointer == story.data[pointer.i]:
			main = story.system.main
		else:
			main = story.data[pointer.i + 1]

		return main, phrase

	# Obtain Type I, II and III phrasal verbs
	def get_phrasal_verb(story, head):
		particles = TYPE_II_PARTICLES + TYPE_II_PARTICLES_MARGINAL
		phrasal_verb = head
		phrase = []
		vtype = ""

		if MinerHelper.lower(phrasal_verb.right_edge.text) in particles:
			phrasal_verb = phrasal_verb.right_edge
			phrase.append(phrasal_verb)
			vtype = "II"
		else:
			for chunk in story.data.noun_chunks:
				for c in phrasal_verb.children:
					if c == chunk.root.head:
						if not c in story.indicators:
							if c.pos_ == 'PART':
								phrase.append(c)
								vtype = "I"
							if c.pos_ == 'ADP':
								phrase.append(c)
								vtype = "III"
		
		if phrase:
			phrase.insert(0, head)

		return phrase, vtype