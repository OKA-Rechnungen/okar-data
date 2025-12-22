#!/bin/bash
for i in data/editions/1*; do
    newname=W`echo $i|cut -d W -f 2`
    mv $i data/editions/$newname
done
rm -f data/editions/*Ueberschriften*

