#include <stdio.h>
void main(){
	int number,result;
	printf("정수를 입력하시오:");
	scanf("%d",&number);
	result = (80=number)&&(90>number);
	printf("입력한 정수 %d의 논리 연산결과:%d",number,result);
}
