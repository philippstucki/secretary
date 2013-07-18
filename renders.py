#!/usr/bin/python
# -*- encoding: utf-8 -*-

 # * Copyright (c) 2012 Christopher Ramírez blindedbythedark [at} gmail (dot] com.
 # * All rights reserved.
 # *  
 # * Permission is hereby granted, free of charge, to any person obtaining a
 # * copy of this software and associated documentation files (the "Software"), 
 # * to deal in the Software without restriction, including without limitation 
 # * the rights to use, copy, modify, merge, publish, distribute, sublicense, 
 # * and/or sell copies of the Software, and to permit persons to whom the 
 # * Software is furnished to do so, subject to the following conditions:
 # *  
 # * The above copyright notice and this permission notice shall be included in
 # * all copies or substantial portions of the Software.
 # *  
 # * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 # * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
 # * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 # * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
 # * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING 
 # * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
 # * DEALINGS IN THE SOFTWARE.

"""
Secretary
Take the power of Jinja2 templates to OpenOffice and LibreOffice.

This file implements BaseRender. BaseRender prepares a XML which describes
ODT document content to be processed by jinja2 or Django template system.  
"""

import re
import os
import sys
import logging
import zipfile
import StringIO
import xml.dom.minidom
from os.path import isfile
from jinja2 import Environment, Undefined


PARAGRAPH_TAG = '{% control_paragraph %}'
TABLEROW_TAG = '{% control_tablerow %}'
TABLECELL_TAG = '{% control_tablecell %}'

OOO_PARAGRAPH_NODE = 'text:p'
OOO_TABLEROW_NODE = 'table:table-row'
OOO_TABLECELL_NODE = 'table:table-cell'


# Silently undefined,
# see http://stackoverflow.com/questions/6182498/jinja2-how-to-make-it-fail-silently-like-djangotemplate
def silently_undefined(*args, **kwargs):
    return u''

return_new = lambda *args, **kwargs: UndefinedSilently()

class UndefinedSilently(Undefined):
    __unicode__ = silently_undefined
    __str__ = silently_undefined
    __call__ = return_new
    __getattr__ = return_new

# ************************************************
# 
#           SECRETARY FILTERS
# 
# ************************************************

def pad_string(value, length=5):
    value = str(value)
    return value.zfill(length)


class BaseRender():
    """
        Prapares a XML string or file to be processed by a templating system.
        
        Use example:
        render = BaseRender('content/xml', var1, var2.. varN)
        render.render
    """

    def __init__(self, xml_doc, template_args):
        self.template_vars = template_args
        self.xml_document = xml.dom.minidom.parseString(xml_doc)
        self.debug = template_args.get('debug', False)

        body = self.xml_document.getElementsByTagName('office:body') or \
               self.xml_document.getElementsByTagName('office:master-styles') 

        self.content_body = body and body[0]

    # ------------------------------------------------------------------------@


    def get_parent_of(self, node, parent_type):
        """
            Returns the first node's parent with name  of parent_type
            If parent "text:p" is not found, returns None.
        """

        if hasattr(node, 'parentNode'):
            if node.parentNode.nodeName.lower() == parent_type:
                return node.parentNode
            else:
                return self.get_parent_of(node.parentNode, parent_type)
        else:
            return None

    # ------------------------------------------------------------------------@


    def render_with_engine(self):
        """
            Once the XML have been prepared, this routine is called
            to do the actual rendering.
        """
        
        environment = Environment(undefined=UndefinedSilently)
        environment.filters['pad'] = pad_string

        template = environment.from_string(self.xml_document.toxml())
        rendered = template.render(**self.template_vars)

        # Replace all \n in field values with a ODT line break
        rendered = rendered.replace('\n', '<text:line-break/>')

        # if self.debug:
        #     # Return a indented XML
        #     return xml.dom.minidom.parseString(
        #         rendered.encode('ascii', 'xmlcharrefreplace')).toprettyxml()


        return rendered


    # -----------------------------------------------------------------------

    def create_text_span_node(self, content):
        span = self.xml_document.createElement('text:span')
        text_node = self.create_text_node(content)
        span.appendChild(text_node)

        return span

    def create_text_node(self, text):
        """
        Creates a text node
        """
        return self.xml_document.createTextNode(text)


    def prepare_document(self):
        """
            Search in every field node in the document and
            replace it with a <text:span> field
        """
        fields = self.content_body.getElementsByTagName('text:text-input')

        for field in fields:
            if field.hasChildNodes():
                field_content = field.childNodes[0].data

                jinja_tags = re.findall(r'(\{.*?\}*})', field_content)
                if not jinja_tags:
                    # Field does not contains jinja template tags
                    continue

                field_description = field.getAttribute('text:description')

                if not field_description:
                    new_node = self.create_text_span_node(field_content)
                else:
                    if field_description in \
                        ['text:p', 'table:table-row', 'table:table-cell']:
                        field = self.get_parent_of(field, field_description)

                    new_node = self.create_text_node(field_content)

                parent = field.parentNode
                parent.insertBefore(new_node, field)
                parent.removeChild(field)
            

    def render(self):
        """
            render prepares the XML and the call render_with_engine
            to parse template engine tags
        """
        
        self.prepare_document()
        return self.render_with_engine()

    # -----------------------------------------------------------------------


def render_template(template, **kwargs):
    """
        Renders *template* file using *kwargs* variables.
        Returns the ODF file generated.
    """
    input_template = StringIO.StringIO(template)
    input = zipfile.ZipFile(input_template, "r" )
    rendered = StringIO.StringIO()
    output = zipfile.ZipFile(rendered, 'a')
       
    # go through the files in source
    for zi in input.filelist:
        out = input.read( zi.filename )

        if zi.filename in ('content.xml', 'styles.xml'):
            render = BaseRender(out, kwargs)
            out = render.render().encode('ascii', 'xmlcharrefreplace')

        elif zi.filename == 'mimetype':
            # mimetype is stored within the ODF
            mimetype = out 

        if sys.version_info >= (2, 7):
            output.writestr(zi.filename, out, zipfile.ZIP_DEFLATED)
        else:
            output.writestr(zi.filename, out)

    # close and finish
    input.close()
    output.close()
    
    return rendered.getvalue()


def render_template_file(file, **kwargs):
    """
        Render a ODF template file
    """

    template_string = StringIO.StringIO()
    template_string.write(file)

    return render_template(template_string, **kwargs)


if __name__ == "__main__":
    from sys import argv
    from datetime import datetime

    document = {
        'datetime': datetime.now()
    }

    countries = [
        {'country': 'United States', 'capital': 'Washington', 'cities': ['miami', 'new york', 'california', 'texas', 'atlanta']},
        {'country': 'England', 'capital': 'London', 'cities': ['gales']},
        {'country': 'Japan', 'capital': 'Tokio', 'cities': ['hiroshima', 'nagazaki']},
        {'country': 'Nicaragua', 'capital': 'Managua', 'cities': [u'león', 'granada', 'masaya']},
        {'country': 'Argentina', 'capital': 'Buenos aires'},
        {'country': 'Chile', 'capital': 'Santiago'},
        {'country': 'Mexico', 'capital': 'MExico City', 'cities': ['puebla', 'cancun']},
    ]

    # ODF is just a zipfile
    input = zipfile.ZipFile( 'simple_template.odt', "r" )
    
    if len(argv) > 1:
        if isfile(argv[1]):
            input = zipfile.ZipFile(argv[1])


    text = open('rendered.odt', 'wb')
    output = zipfile.ZipFile( text, "w" )
       
    # go through the files in input
    for zi in input.filelist:
        out = input.read( zi.filename )

        if zi.filename == 'content.xml':
            render = BaseRender(out, document=document, countries=countries)
            out = render.render().encode('ascii', 'xmlcharrefreplace')

        elif zi.filename == 'mimetype':
            # mimetype is stored within the ODF
            mimetype = out 

        output.writestr( zi.filename, out,
                         zipfile.ZIP_DEFLATED )

    # close and finish
    input.close()
    output.close()

    print "Template rendering finished! Check rendered.odt file."

    
    
