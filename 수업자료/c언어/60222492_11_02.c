#include <stdio.h>

void star(int i){
	int j;
	for(j = 1; j <= i; j++){
		printf("*");
	}
}

void main() {
	int number;
	printf("정수를 입력하시오:");
	scanf("%d", &number);
	star(number);
}
