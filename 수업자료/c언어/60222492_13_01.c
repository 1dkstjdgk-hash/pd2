#include <stdio.h>

void main() {
	double real[3] = {10.5,20.5,30.5};
	int i;
	for(i = 0; i <3; i++){
		printf("%d번째 공간에 저장된 수:%lf\n",i+1,real[i]);
		
	}
}
