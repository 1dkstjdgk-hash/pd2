#include <stdio.h>
void numberDecision(int i){
	if(i > 0)
		printf("양수 입력!");
	else if(i < 0)
		printf("음수 입력!");
	else
		printf("0 입력!"); 
}
void main() {
	int number;
	printf("정수를 입력하시오:");
	scanf("%d", &number);
	numberDecision(number);
}
